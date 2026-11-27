import type { ApiClient } from '@/shared/api';
import type { Usage } from '@/shared/api/types';

/** GetUsage: the tokens this week's recorded steps spent (D-358d). */
export async function getUsage(api: ApiClient, signal?: AbortSignal): Promise<Usage> {
    const response = await api.request<Usage>('agent', 'GET', '/api/v1/usage', { signal });
    return response.data;
}
