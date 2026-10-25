import { ApiError } from '@/shared/api';
import type { ApiClient } from '@/shared/api';

/** The CBOM (CycloneDX) of a scan as the service stores it; null when no CBOM was recorded for the scan. */
export async function downloadCbom(api: ApiClient, scanId: string): Promise<Blob | null> {
    try {
        const body = await api.download(
            'core',
            `/api/v1/scans/${encodeURIComponent(scanId)}/artifact`,
            'application/vnd.cyclonedx+json, application/json',
        );
        return body.blob;
    } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
    }
}
