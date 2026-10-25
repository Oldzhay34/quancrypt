import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from './client';

function clientWith(response: () => Response | Promise<Response>) {
    const fetchImpl = vi.fn(async () => response());
    const client = createApiClient({
        getToken: () => 'T'.repeat(43),
        getLanguage: () => 'tr',
        onUnauthorized: vi.fn(),
        fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    return { client, fetchImpl };
}

describe('api client: downloads', () => {
    it('reads a file or text body with the requested Accept, the bearer token and no credentials', async () => {
        const { client, fetchImpl } = clientWith(
            () => new Response('# report', { status: 200, headers: { 'Content-Type': 'text/markdown' } }),
        );

        const body = await client.download('core', '/api/v1/scans/s/plan/report', 'text/markdown');

        expect(await body.blob.text()).toBe('# report');
        expect(body.contentType).toBe('text/markdown');
        const [url, init] = fetchImpl.mock.calls[0] as unknown as [URL, RequestInit];
        const headers = init.headers as Record<string, string>;
        expect(init.method).toBe('GET');
        expect(headers.Accept).toBe('text/markdown');
        expect(headers.Authorization).toBe(`Bearer ${'T'.repeat(43)}`);
        expect(init.credentials).toBe('omit');
        expect(url.href).not.toContain('T'.repeat(43));
    });

    it('lets a caller override the language of one request', async () => {
        const { client, fetchImpl } = clientWith(() => new Response('x', { status: 200 }));

        await client.download('core', '/x', 'text/markdown', { headers: { 'Accept-Language': 'en' } });

        const [, init] = fetchImpl.mock.calls[0] as unknown as [URL, RequestInit];
        expect((init.headers as Record<string, string>)['Accept-Language']).toBe('en');
    });

    it('raises the problem of a refused download like any other request', async () => {
        const { client } = clientWith(
            () =>
                new Response(JSON.stringify({ type: 'https://quancrypt.local/problems/not-found' }), {
                    status: 404,
                    headers: { 'Content-Type': 'application/problem+json' },
                }),
        );

        await expect(client.download('core', '/x', 'application/json')).rejects.toMatchObject({
            status: 404,
            code: 'not-found',
        });
    });
});

describe('api client: probe', () => {
    it('is true for any answer and sends no token, cookie or custom header', async () => {
        const { client, fetchImpl } = clientWith(() => new Response('', { status: 200 }));

        expect(await client.probe('http://127.0.0.1:8088', 2000)).toBe(true);

        const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toBe('http://127.0.0.1:8088');
        expect(init.mode).toBe('no-cors');
        expect(init.credentials).toBe('omit');
        // A browser refuses a no-cors request with any redirect mode but follow (found on the live stack).
        expect(init.redirect).toBe('follow');
        expect(init.headers).toBeUndefined();
    });

    it('is false when the connection fails', async () => {
        const { client } = clientWith(() => {
            throw new TypeError('connection refused');
        });

        expect(await client.probe('http://127.0.0.1:8088', 2000)).toBe(false);
    });

    it('is false when nothing answers within the time limit', async () => {
        const fetchImpl = vi.fn(
            (_url: string, init: RequestInit) =>
                new Promise<Response>((_resolve, reject) => {
                    init.signal?.addEventListener('abort', () =>
                        reject(new DOMException('aborted', 'AbortError')),
                    );
                }),
        );
        const client = createApiClient({
            getToken: () => null,
            getLanguage: () => 'tr',
            onUnauthorized: vi.fn(),
            fetchImpl: fetchImpl as unknown as typeof fetch,
        });

        expect(await client.probe('http://127.0.0.1:8088', 20)).toBe(false);
    });
});
