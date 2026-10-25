import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useApi } from '@/shared/api';
import type { Finding, PlanItem } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { useScanFindings } from '@/shared/scan';
import { getPlan, getPlanReport, transitionPlanItem } from './api';

/** A plan item with the finding it is about. */
export interface PlanRow {
    item: PlanItem;
    finding: Finding | null;
}

/** Highest risk first; equal scores by file path, then by id, so the order never jumps between reads. */
export function sortRows(rows: readonly PlanRow[]): PlanRow[] {
    return [...rows].sort(
        (a, b) =>
            b.item.riskScore - a.item.riskScore ||
            (a.finding?.path ?? '').localeCompare(b.finding?.path ?? '') ||
            a.item.id.localeCompare(b.item.id),
    );
}

export function usePlan(scanId: string) {
    const api = useApi();
    const plan = useQuery({
        queryKey: ['scan', scanId, 'plan'],
        queryFn: ({ signal }) => getPlan(api, scanId, signal),
    });
    const findings = useScanFindings(scanId);
    const rows = useMemo(() => {
        if (!plan.data || !findings.data) return null;
        const byId = new Map(findings.data.map((finding) => [finding.id, finding]));
        return sortRows(plan.data.items.map((item) => ({ item, finding: byId.get(item.findingId) ?? null })));
    }, [plan.data, findings.data]);
    return { plan, findings, rows };
}

/** The Markdown report, in the interface language. */
export function usePlanReport(scanId: string) {
    const api = useApi();
    const { language } = useI18n();
    return useQuery({
        queryKey: ['scan', scanId, 'plan-report', language],
        queryFn: ({ signal }) => getPlanReport(api, scanId, language, signal),
    });
}

/** Approves an item (PLANNED to APPROVED); the plan and the report are read again afterwards, also after a refused change. */
export function useApprove(scanId: string) {
    const api = useApi();
    const client = useQueryClient();
    const refresh = () =>
        Promise.all([
            client.invalidateQueries({ queryKey: ['scan', scanId, 'plan'] }),
            client.invalidateQueries({ queryKey: ['scan', scanId, 'plan-report'] }),
        ]);
    return useMutation({
        mutationFn: (item: PlanItem) => transitionPlanItem(api, item, 'APPROVED'),
        onSettled: refresh,
    });
}
