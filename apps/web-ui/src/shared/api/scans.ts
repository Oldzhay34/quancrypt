import { ApiError } from './client';
import type { ApiClient } from './client';
import type { Scan, ScanPage, ScanSummary, Topology } from './types';

export async function listScans(api: ApiClient, projectId: string, signal?: AbortSignal): Promise<Scan[]> {
    const response = await api.request<ScanPage>(
        'core',
        'GET',
        `/api/v1/projects/${encodeURIComponent(projectId)}/scans`,
        { query: { page: 0, size: 20 }, signal },
    );
    return response.data.items;
}

export async function getScanSummary(
    api: ApiClient,
    scanId: string,
    signal?: AbortSignal,
): Promise<ScanSummary> {
    const response = await api.request<ScanSummary>(
        'core',
        'GET',
        `/api/v1/scans/${encodeURIComponent(scanId)}`,
        { signal },
    );
    return response.data;
}

/** The scan's topology, or null when none was recorded (a scan whose topology step failed). */
export async function getTopology(
    api: ApiClient,
    scanId: string,
    signal?: AbortSignal,
): Promise<Topology | null> {
    try {
        const response = await api.request<Topology>(
            'core',
            'GET',
            `/api/v1/scans/${encodeURIComponent(scanId)}/topology`,
            { signal },
        );
        return response.data;
    } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
    }
}
