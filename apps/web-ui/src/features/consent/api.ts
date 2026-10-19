import type { ApiClient } from '@/shared/api';
import type { Consent, ConsentType, PrivacyNotice } from '@/shared/api/types';

export async function getPrivacyNotice(api: ApiClient, signal?: AbortSignal): Promise<PrivacyNotice> {
    return (await api.request<PrivacyNotice>('core', 'GET', '/api/v1/privacy-notices/latest', { signal }))
        .data;
}

export async function getConsents(
    api: ApiClient,
    projectId: string,
    signal?: AbortSignal,
): Promise<Consent[]> {
    const response = await api.request<{ items: Consent[] }>(
        'core',
        'GET',
        `/api/v1/projects/${encodeURIComponent(projectId)}/consents`,
        { signal },
    );
    return response.data.items;
}

/** First grant, or the grant of a withdrawn consent (then `ifMatchVersion` is the consent's version). */
export async function grantConsent(
    api: ApiClient,
    projectId: string,
    consentType: ConsentType,
    privacyNoticeVersion: number,
    ifMatchVersion?: number,
): Promise<Consent> {
    const response = await api.request<Consent>(
        'core',
        'POST',
        `/api/v1/projects/${encodeURIComponent(projectId)}/consents`,
        {
            body: { consentType, privacyNoticeVersion },
            headers: ifMatchVersion === undefined ? undefined : { 'If-Match': `"${ifMatchVersion}"` },
            idempotencyKey: true,
        },
    );
    return response.data;
}

export async function revokeConsent(
    api: ApiClient,
    projectId: string,
    consentType: ConsentType,
    ifMatchVersion: number,
): Promise<Consent> {
    const response = await api.request<Consent>(
        'core',
        'DELETE',
        `/api/v1/projects/${encodeURIComponent(projectId)}/consents/${consentType}`,
        { headers: { 'If-Match': `"${ifMatchVersion}"` } },
    );
    return response.data;
}
