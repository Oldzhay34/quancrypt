import { useQuery } from '@tanstack/react-query';
import { listScans, useApi } from '@/shared/api';
import type { Scan } from '@/shared/api/types';

/**
 * The project's newest completed scan, or null when it was never scanned. The inventory, topology and plan screens all show this
 * scan. The key starts with `['scan-summary', projectId]`, so the chat's invalidation after a new scan refreshes it too.
 */
export function useLatestCompletedScan(projectId: string) {
    const api = useApi();
    return useQuery({
        queryKey: ['scan-summary', projectId, 'latest'],
        queryFn: async ({ signal }): Promise<Scan | null> => {
            const scans = await listScans(api, projectId, signal);
            return scans.find((scan) => scan.status === 'COMPLETED') ?? null;
        },
    });
}
