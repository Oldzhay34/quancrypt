import { describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from './client';

function clientWith(response: () => Response | Promise<Response>, onUnauthorized = vi.fn()) {
    const fetchImpl = vi.fn(async () => response());
    const client = createApiClient({
        getToken: () => 'T'.repeat(43),
        getLanguage: () => 'en',
        onUnauthorized,
        fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    return { client, fetchImpl, onUnauthorized };
}

const problem = (status: number, type: string) =>
    new Response(JSON.stringify({ type }), {
        status,
        headers: { 'Content-Type': 'application/problem+json' },
    });

describe('api client', () => {
    it('sends the token only as a bearer header, with trace id, language and no credentials', async () => {
        const { client, fetchImpl } = clientWith(
            () =>
                new Response('{"ok":true}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
        );

        const result = await client.request<{ ok: boolean }>('core', 'GET', '/api/v1/projects', {
            query: { page: 0, size: 200 },
        });

        expect(result.data.ok).toBe(true);
        const [url, init] = fetchImpl.mock.calls[0] as unknown as [URL, RequestInit];
        expect(url.href).toBe('http://127.0.0.1:8081/api/v1/projects?page=0&size=200');
        const headers = init.headers as Record<string, string>;
        expect(headers.Authorization).toBe(`Bearer ${'T'.repeat(43)}`);
        expect(headers['Accept-Language']).toBe('en');
        expect(headers['X-Trace-Id']).toMatch(/^[0-9a-f]{32}$/);
        expect(init.credentials).toBe('omit');
        expect(url.href).not.toContain('T'.repeat(43));
    });

    it('talks to the agent on port 8083 and adds an Idempotency-Key to commands', async () => {
        const { client, fetchImpl } = clientWith(() => new Response(null, { status: 204 }));

        await client.request('agent', 'POST', '/api/v1/sessions/s/stop', { idempotencyKey: true });

        const [url, init] = fetchImpl.mock.calls[0] as unknown as [URL, RequestInit];
        expect(url.origin).toBe('http://127.0.0.1:8083');
        expect((init.headers as Record<string, string>)['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
    });

    it('reports a 401 and raises the problem code, never the server text', async () => {
        const { client, onUnauthorized } = clientWith(() =>
            problem(401, 'https://quancrypt.local/problems/unauthorized'),
        );

        await expect(client.request('core', 'GET', '/api/v1/projects')).rejects.toMatchObject({
            status: 401,
            code: 'unauthorized',
        });
        expect(onUnauthorized).toHaveBeenCalledTimes(1);
    });

    it('maps a conflict problem to its code without a 401 report', async () => {
        const { client, onUnauthorized } = clientWith(() =>
            problem(409, 'https://quancrypt.local/problems/concurrent-modification'),
        );

        const error = await client.request('core', 'POST', '/x').catch((caught: unknown) => caught);

        expect(error).toBeInstanceOf(ApiError);
        expect((error as ApiError).code).toBe('concurrent-modification');
        expect(onUnauthorized).not.toHaveBeenCalled();
    });

    it('turns an unreachable service into a network error', async () => {
        const { client } = clientWith(() => {
            throw new TypeError('failed to fetch');
        });

        await expect(client.request('core', 'GET', '/x')).rejects.toMatchObject({
            status: 0,
            code: 'network',
        });
    });
});
