import { useQuery } from '@tanstack/react-query';
import { useApi } from '@/shared/api';

/** The dashboard (Apache Superset, `data` profile) listens here; the address is fixed and also named in the page's CSP (`connect-src`). */
export const SUPERSET_URL = 'http://127.0.0.1:8088';

/** True while Superset answers. It is asked about every 30 seconds; a failure or silence for 2 seconds means "not running". */
export function useSupersetReachable(): boolean {
    const api = useApi();
    const query = useQuery({
        queryKey: ['superset-reachable'],
        queryFn: () => api.probe(SUPERSET_URL, 2000),
        staleTime: 30_000,
        refetchInterval: 30_000,
        retry: false,
    });
    return query.data === true;
}
