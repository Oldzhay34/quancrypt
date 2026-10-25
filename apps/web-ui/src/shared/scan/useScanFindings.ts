import { useQuery } from '@tanstack/react-query';
import { listAllFindings, useApi } from '@/shared/api';
import type { FindingQuery } from '@/shared/api/findings';

/** All findings of a scan under the server-side filters (the inventory and the topology panel use the same list). */
export function useScanFindings(scanId: string, query: FindingQuery = {}) {
    const api = useApi();
    return useQuery({
        queryKey: ['scan', scanId, 'findings', query],
        queryFn: ({ signal }) => listAllFindings(api, scanId, query, signal),
    });
}
