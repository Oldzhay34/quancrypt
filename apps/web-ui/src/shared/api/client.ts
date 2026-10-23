/** Typed `fetch` wrapper for the two services (OpenAPI types in ./generated). The token is only ever put in the Authorization header. */

export type Service = 'core' | 'agent';

/** Fixed addresses: the nginx CSP `connect-src` allows exactly these two origins (P5.2). */
export const SERVICE_BASES: Record<Service, string> = {
    core: 'http://127.0.0.1:8081',
    agent: 'http://127.0.0.1:8083',
};

export class ApiError extends Error {
    readonly status: number;
    /** Last segment of the RFC 9457 `type` (for example `concurrent-modification`); `network` when nothing answered. */
    readonly code: string;
    readonly traceId: string | null;

    constructor(status: number, code: string, message: string, traceId: string | null) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.code = code;
        this.traceId = traceId;
    }
}

export interface RequestOptions {
    body?: unknown;
    query?: Record<string, string | number | undefined>;
    headers?: Record<string, string>;
    /** Command POST/PUT/DELETE: sends an `Idempotency-Key` (a given one, or a fresh UUID). */
    idempotencyKey?: string | true;
    signal?: AbortSignal;
}

export interface ApiResponse<T> {
    data: T;
    status: number;
    headers: Headers;
}

export interface ApiClient {
    request<T>(
        service: Service,
        method: string,
        path: string,
        options?: RequestOptions,
    ): Promise<ApiResponse<T>>;
    /**
     * Opens a server-sent event stream (P5.3): the same headers, bearer token and error handling as `request`, and the body to be
     * read with `readSseStream`. A 2xx answer that is not `text/event-stream` is refused (`protocol`).
     */
    stream(
        service: Service,
        method: string,
        path: string,
        options?: RequestOptions,
    ): Promise<ReadableStream<Uint8Array>>;
}

export interface ClientConfig {
    getToken: () => string | null;
    getLanguage: () => string;
    onUnauthorized: () => void;
    fetchImpl?: typeof fetch;
}

function newTraceId(): string {
    return crypto.randomUUID().replaceAll('-', '');
}

function problemCode(type: unknown): string {
    if (typeof type !== 'string') return 'unknown';
    return type.slice(type.lastIndexOf('/') + 1) || 'unknown';
}

export function createApiClient(config: ClientConfig): ApiClient {
    const doFetch = config.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));

    /** One request; returns a 2xx response, raises `ApiError` otherwise. */
    async function send(
        service: Service,
        method: string,
        path: string,
        options: RequestOptions,
        accept: string,
    ): Promise<Response> {
        const url = new URL(SERVICE_BASES[service] + path);
        for (const [name, value] of Object.entries(options.query ?? {})) {
            if (value !== undefined) url.searchParams.set(name, String(value));
        }
        const headers: Record<string, string> = {
            Accept: accept,
            'Accept-Language': config.getLanguage(),
            'X-Trace-Id': newTraceId(),
            ...options.headers,
        };
        const token = config.getToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        if (options.idempotencyKey) {
            headers['Idempotency-Key'] =
                options.idempotencyKey === true ? crypto.randomUUID() : options.idempotencyKey;
        }
        if (options.body !== undefined) headers['Content-Type'] = 'application/json';

        let response: Response;
        try {
            response = await doFetch(url, {
                method,
                headers,
                body: options.body === undefined ? undefined : JSON.stringify(options.body),
                signal: options.signal,
                credentials: 'omit',
                redirect: 'error',
                cache: 'no-store',
            });
        } catch (error) {
            // A caller's own cancellation is not a network failure: it passes through untouched.
            if (options.signal?.aborted) throw error;
            throw new ApiError(0, 'network', 'network', null);
        }

        if (!response.ok) {
            const traceId = response.headers.get('X-Trace-Id');
            if (response.status === 401) config.onUnauthorized();
            let code = 'unknown';
            try {
                const problem: unknown = await response.json();
                if (problem && typeof problem === 'object')
                    code = problemCode((problem as { type?: unknown }).type);
            } catch {
                // Not a problem document.
            }
            throw new ApiError(response.status, code, `HTTP ${response.status}`, traceId);
        }
        return response;
    }

    return {
        async request<T>(service: Service, method: string, path: string, options: RequestOptions = {}) {
            const response = await send(service, method, path, options, 'application/json');
            const hasBody =
                response.status !== 204 && (response.headers.get('Content-Type') ?? '').includes('json');
            const data = (hasBody ? await response.json() : undefined) as T;
            return { data, status: response.status, headers: response.headers };
        },

        async stream(service: Service, method: string, path: string, options: RequestOptions = {}) {
            const response = await send(service, method, path, options, 'text/event-stream');
            const traceId = response.headers.get('X-Trace-Id');
            const isStream = (response.headers.get('Content-Type') ?? '').startsWith('text/event-stream');
            if (!isStream || response.body === null) {
                await response.body?.cancel().catch(() => undefined);
                throw new ApiError(response.status, 'protocol', 'not an event stream', traceId);
            }
            return response.body;
        },
    };
}
