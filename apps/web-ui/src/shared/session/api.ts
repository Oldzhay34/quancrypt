import type { ApiClient } from '../api/client';

/** StopSession: ends the running answer or scan of the session. 204, and idempotent when nothing runs. */
export async function stopSession(api: ApiClient, sessionId: string): Promise<void> {
    await api.request<void>('agent', 'POST', `/api/v1/sessions/${encodeURIComponent(sessionId)}/stop`);
}
