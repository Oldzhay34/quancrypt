import type { ApiClient } from './client';
import type { Finding, FindingPage } from './types';

const PAGE_SIZE = 200;
/** A scan holds at most 500 findings (D-141), so three pages are the most there can be; ten is a safety stop. */
const MAX_PAGES = 10;

/** The server-side filters of `ListFindings`; an absent key means "any". */
export type FindingQuery = Partial<
    Record<'priority' | 'algorithmFamily' | 'usageContext' | 'locationKind', string>
>;

/** Every finding of a scan that matches the filters, read page by page. */
export async function listAllFindings(
    api: ApiClient,
    scanId: string,
    query: FindingQuery = {},
    signal?: AbortSignal,
): Promise<Finding[]> {
    const findings: Finding[] = [];
    for (let page = 0; page < MAX_PAGES; page++) {
        const response = await api.request<FindingPage>(
            'core',
            'GET',
            `/api/v1/scans/${encodeURIComponent(scanId)}/findings`,
            { query: { ...query, page, size: PAGE_SIZE }, signal },
        );
        findings.push(...response.data.items);
        if (findings.length >= response.data.totalElements || response.data.items.length === 0) break;
    }
    return findings;
}
