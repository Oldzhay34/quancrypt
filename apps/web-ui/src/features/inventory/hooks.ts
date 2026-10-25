import { useMutation, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { getScanSummary, useApi } from '@/shared/api';
import { saveFile } from '@/shared/download';
import { useScanFindings } from '@/shared/scan';
import { downloadCbom } from './api';
import { emptyFilter, paginate, serverQuery, visible } from './filters';
import type { FindingFilter } from './filters';

export function useScanSummary(scanId: string) {
    const api = useApi();
    return useQuery({
        queryKey: ['scan', scanId, 'summary'],
        queryFn: ({ signal }) => getScanSummary(api, scanId, signal),
    });
}

/** The filter, the filtered findings of a scan and the page of them on show. Changing the filter returns to the first page. */
export function useInventory(scanId: string) {
    const [filter, setFilterState] = useState<FindingFilter>(emptyFilter);
    const [page, setPage] = useState(0);
    const findings = useScanFindings(scanId, serverQuery(filter));
    const shown = useMemo(() => visible(findings.data ?? [], filter), [findings.data, filter]);
    const paged = paginate(shown, page);
    return {
        filter,
        setFilter: (next: FindingFilter) => {
            setFilterState(next);
            setPage(0);
        },
        page: paged.page,
        pages: paged.pages,
        setPage,
        rows: paged.items,
        total: shown.length,
        findings,
    };
}

/** Saves the scan's CBOM as a file; the result is `missing` when the scan has none. */
export function useCbomDownload(scanId: string) {
    const api = useApi();
    return useMutation({
        mutationFn: async () => {
            const blob = await downloadCbom(api, scanId);
            if (blob === null) return 'missing' as const;
            saveFile(blob, `quancrypt-cbom-${scanId.slice(0, 8)}.cdx.json`);
            return 'saved' as const;
        },
    });
}
