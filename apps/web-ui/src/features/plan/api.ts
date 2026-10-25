import { ApiError } from '@/shared/api';
import type { ApiClient } from '@/shared/api';
import type { Plan, PlanItem, PlanPage, PlanState } from '@/shared/api/types';

const PAGE_SIZE = 200;
/** A plan holds at most 500 items (D-138): three pages; ten is a safety stop. */
const MAX_PAGES = 10;

export interface LoadedPlan {
    plan: Plan;
    items: PlanItem[];
}

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;

/** The plan of a scan with all its items; null when the scan has no plan yet. */
export async function getPlan(
    api: ApiClient,
    scanId: string,
    signal?: AbortSignal,
): Promise<LoadedPlan | null> {
    const items: PlanItem[] = [];
    let plan: Plan | null = null;
    try {
        for (let page = 0; page < MAX_PAGES; page++) {
            const response = await api.request<PlanPage>(
                'core',
                'GET',
                `/api/v1/scans/${encodeURIComponent(scanId)}/plan`,
                { query: { page, size: PAGE_SIZE }, signal },
            );
            plan = response.data.plan;
            items.push(...response.data.items);
            if (items.length >= response.data.totalElements || response.data.items.length === 0) break;
        }
    } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
    }
    return plan === null ? null : { plan, items };
}

/** The Markdown report of the plan in the given language (`tr` or `en`); null when there is no plan. */
export async function getPlanReport(
    api: ApiClient,
    scanId: string,
    language: string,
    signal?: AbortSignal,
): Promise<string | null> {
    try {
        const body = await api.download(
            'core',
            `/api/v1/scans/${encodeURIComponent(scanId)}/plan/report`,
            'text/markdown',
            { headers: { 'Accept-Language': language }, signal },
        );
        return await body.blob.text();
    } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
    }
}

/** Moves one item to another state; `version` is the one the item had when it was read (`If-Match`, optimistic lock). */
export async function transitionPlanItem(
    api: ApiClient,
    item: Pick<PlanItem, 'id' | 'version'>,
    toState: PlanState,
): Promise<PlanItem> {
    const response = await api.request<PlanItem>(
        'core',
        'POST',
        `/api/v1/plan-items/${encodeURIComponent(item.id)}/transitions`,
        { body: { toState }, headers: { 'If-Match': `"${item.version}"` }, idempotencyKey: true },
    );
    return response.data;
}
