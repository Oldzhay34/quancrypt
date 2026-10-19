import type { ApiClient } from '../api/client';
import type { ProjectPage } from '../api/types';

export async function listProjects(api: ApiClient, signal?: AbortSignal) {
    const response = await api.request<ProjectPage>('core', 'GET', '/api/v1/projects', {
        query: { page: 0, size: 200 },
        signal,
    });
    return response.data.items;
}
