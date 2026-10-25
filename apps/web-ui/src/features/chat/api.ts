import type { ApiClient } from '@/shared/api';
import type {
    ChatMessage,
    ClarificationAnswer,
    ClarificationList,
    MessagePage,
    Session,
} from '@/shared/api/types';

const PAGE_SIZE = 200;
const MAX_PAGES = 20;

export async function createSession(api: ApiClient, projectId: string, language: string): Promise<Session> {
    const response = await api.request<Session>('agent', 'POST', '/api/v1/sessions', {
        body: { project_id: projectId, language },
        idempotencyKey: true,
    });
    return response.data;
}

/** The whole history, oldest first (pages of 200, at most 20 pages). */
export async function listMessages(
    api: ApiClient,
    sessionId: string,
    signal?: AbortSignal,
): Promise<ChatMessage[]> {
    const messages: ChatMessage[] = [];
    for (let page = 0; page < MAX_PAGES; page++) {
        const response = await api.request<MessagePage>(
            'agent',
            'GET',
            `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`,
            { query: { page, size: PAGE_SIZE }, signal },
        );
        messages.push(...response.data.items);
        if (messages.length >= response.data.total || response.data.items.length === 0) break;
    }
    return messages;
}

export async function deleteSession(api: ApiClient, sessionId: string): Promise<void> {
    await api.request<void>('agent', 'DELETE', `/api/v1/sessions/${encodeURIComponent(sessionId)}`);
}

export function streamMessage(
    api: ApiClient,
    sessionId: string,
    content: string,
    signal: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
    return api.stream('agent', 'POST', `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`, {
        body: { content },
        signal,
    });
}

export function streamInitialScan(
    api: ApiClient,
    sessionId: string,
    root: string,
    signal: AbortSignal,
): Promise<ReadableStream<Uint8Array>> {
    return api.stream('agent', 'POST', `/api/v1/sessions/${encodeURIComponent(sessionId)}/initial-scan`, {
        body: { root },
        signal,
    });
}

export async function answerClarifications(
    api: ApiClient,
    sessionId: string,
    answers: ClarificationAnswer[],
): Promise<ClarificationList['items']> {
    const response = await api.request<ClarificationList>(
        'agent',
        'POST',
        `/api/v1/sessions/${encodeURIComponent(sessionId)}/clarifications`,
        { body: { answers }, idempotencyKey: true },
    );
    return response.data.items;
}
