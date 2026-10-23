import type { ChatMessage, Consent, Project, Scan, ScanSummary, Topology } from '@/shared/api/types';

export const TOKEN = 'A'.repeat(43);
export const PROJECT: Project = {
    id: '11111111-1111-4111-8111-111111111111',
    projectKey: 'k',
    displayName: 'qbank',
    createdAt: '2026-10-19T10:00:00Z',
};
export const NOTICE = {
    version: 2,
    textTr: 'Aydınlatma metni v2\nİkinci satır',
    textEn: 'Privacy notice v2\nSecond line',
    publishedAt: '2026-10-19T00:00:00Z',
};

export interface Call {
    method: string;
    url: URL;
    headers: Headers;
    body: unknown;
}

function json(status: number, body: unknown, type = 'application/json'): Response {
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } });
}

function problem(status: number, code: string): Response {
    return json(status, { type: `https://quancrypt.local/problems/${code}` }, 'application/problem+json');
}

/** One server-sent event as the agent-service writes it. */
export function sse(event: string, data: unknown): string {
    return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** The body of an event stream a test controls: it pushes text when it wants and closes the stream when the turn ends. */
export class StreamHandle {
    cancelled = false;
    closed = false;
    readonly body: ReadableStream<Uint8Array>;
    private controller: ReadableStreamDefaultController<Uint8Array> | null = null;
    private readonly encoder = new TextEncoder();

    constructor(private readonly onClose: () => void) {
        this.body = new ReadableStream<Uint8Array>({
            start: (controller) => {
                this.controller = controller;
            },
            cancel: () => {
                this.cancelled = true;
            },
        });
    }

    push(text: string): void {
        if (this.closed || this.cancelled) return;
        this.controller?.enqueue(this.encoder.encode(text));
    }

    /** Ends the stream; what the turn stored (messages, a scan) becomes visible to the next read. */
    close(): void {
        if (this.closed) return;
        this.closed = true;
        this.onClose();
        if (!this.cancelled) this.controller?.close();
    }
}

interface FakeSession {
    projectId: string;
    messages: ChatMessage[];
}

export interface ScanOverview {
    scan: Scan;
    summary: ScanSummary;
    /** Null: the scan has no recorded topology (the endpoint answers 404). */
    topology: Topology | null;
}

export interface StreamPlan {
    /** Written and closed at once; leave it out to drive the stream with the returned handle. */
    text?: string;
    /** Appended to the session's history when the stream ends. */
    stored?: ChatMessage[];
    /** Runs when the stream ends (a scan stores its result here). */
    onClose?: () => void;
}

interface QueuedStream {
    plan: StreamPlan;
    handle: StreamHandle;
    session: FakeSession | null;
}

export const SESSION_ID = '22222222-2222-4222-8222-222222222222';

/** A stand-in for core-service and agent-service: records every call, answers from mutable state. */
export class FakeBackend {
    calls: Call[] = [];
    projects: Project[] = [PROJECT];
    consents: Consent[] = [];
    notice = NOTICE;
    unauthorized = false;
    failNext: number | null = null;

    // agent-service (chat)
    sessions = new Map<string, FakeSession>();
    /** Streams handed out, in order, to the next message or initial-scan requests. */
    private readonly streams: QueuedStream[] = [];
    /** Set to answer the next stream request with this problem (for example `session-busy` with 409). */
    failStream: { status: number; code: string } | null = null;
    clarificationAnswers: unknown[] = [];
    private nextSession = 0;

    // core-service (scan overview)
    overview: ScanOverview | null = null;

    /** Prepares a session as if it had been opened before (its id is what the browser remembered). */
    addSession(messages: ChatMessage[] = [], id = SESSION_ID): string {
        this.sessions.set(id, { projectId: PROJECT.id, messages });
        return id;
    }

    /** The stream the next message or initial-scan request gets. */
    queueStream(plan: StreamPlan = {}): StreamHandle {
        const entry: QueuedStream = { plan, session: null, handle: null as unknown as StreamHandle };
        entry.handle = new StreamHandle(() => {
            if (entry.session && plan.stored) entry.session.messages.push(...plan.stored);
            plan.onClose?.();
        });
        if (plan.text !== undefined) entry.handle.push(plan.text);
        this.streams.push(entry);
        return entry.handle;
    }

    private openStream(sessionId: string): Response {
        const session = this.sessions.get(sessionId);
        if (!session) return problem(404, 'not-found');
        if (this.failStream) {
            const { status, code } = this.failStream;
            this.failStream = null;
            return problem(status, code);
        }
        const entry = this.streams.shift();
        if (!entry) return problem(500, 'internal-error');
        entry.session = session;
        const { handle, plan } = entry;
        const response = new Response(handle.body, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
        });
        // A prepared text ends the stream right away; otherwise the test closes it.
        if (plan.text !== undefined) queueMicrotask(() => handle.close());
        return response;
    }

    fetch = async (input: URL | RequestInfo, init?: RequestInit): Promise<Response> => {
        const url = new URL(input instanceof URL ? input.href : String(input));
        const headers = new Headers(init?.headers);
        const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined;
        const method = init?.method ?? 'GET';
        this.calls.push({ method, url, headers, body });
        if (this.unauthorized)
            return json(
                401,
                { type: 'https://quancrypt.local/problems/unauthorized' },
                'application/problem+json',
            );
        if (this.failNext !== null) {
            const status = this.failNext;
            this.failNext = null;
            return json(
                status,
                { type: 'https://quancrypt.local/problems/concurrent-modification' },
                'application/problem+json',
            );
        }
        const path = url.pathname;
        if (method === 'GET' && path === '/api/v1/projects')
            return json(200, {
                items: this.projects,
                page: 0,
                size: 200,
                totalElements: this.projects.length,
            });
        if (method === 'GET' && path === '/api/v1/privacy-notices/latest') return json(200, this.notice);
        if (path.endsWith('/consents')) {
            if (method === 'GET') return json(200, { items: this.consents });
            const request = body as { consentType: Consent['consentType']; privacyNoticeVersion: number };
            const old = this.consents.find((c) => c.consentType === request.consentType);
            const next: Consent = {
                consentType: request.consentType,
                privacyNoticeVersion: request.privacyNoticeVersion,
                grantedAt: '2026-10-19T12:00:00Z',
                revokedAt: null,
                version: (old?.version ?? 0) + 1,
            };
            this.consents = [...this.consents.filter((c) => c !== old), next];
            return json(old ? 200 : 201, next);
        }
        const revoke = /\/consents\/([A-Z_]+)$/.exec(path);
        if (method === 'DELETE' && revoke) {
            const old = this.consents.find((c) => c.consentType === revoke[1]);
            if (!old) return json(404, {}, 'application/problem+json');
            const next = { ...old, revokedAt: '2026-10-19T13:00:00Z', version: old.version + 1 };
            this.consents = this.consents.map((c) => (c === old ? next : c));
            return json(200, next);
        }
        if (method === 'POST' && /\/sessions\/[^/]+\/stop$/.test(path))
            return new Response(null, { status: 204 });
        const chat = this.chatRoute(method, path, body);
        if (chat) return chat;
        return json(404, {}, 'application/problem+json');
    };

    /** The chat endpoints of agent-service and the scan endpoints of core-service; null for any other path. */
    private chatRoute(method: string, path: string, body: unknown): Response | null {
        if (method === 'POST' && path === '/api/v1/sessions') {
            const request = body as { project_id: string; language: string };
            const id = `00000000-0000-4000-8000-${String(++this.nextSession).padStart(12, '0')}`;
            this.sessions.set(id, { projectId: request.project_id, messages: [] });
            return json(201, {
                id,
                project_id: request.project_id,
                language: request.language,
                created_at: '2026-10-24T10:00:00Z',
            });
        }
        const session = /^\/api\/v1\/sessions\/([^/]+)(?:\/(messages|initial-scan|clarifications))?$/.exec(
            path,
        );
        if (session) {
            const [, id = '', part] = session;
            const found = this.sessions.get(id);
            if (!found) return problem(404, 'not-found');
            if (!part && method === 'DELETE') {
                this.sessions.delete(id);
                return new Response(null, { status: 204 });
            }
            if (part === 'messages' && method === 'GET')
                return json(200, {
                    items: found.messages,
                    page: 0,
                    size: 200,
                    total: found.messages.length,
                });
            if ((part === 'messages' || part === 'initial-scan') && method === 'POST')
                return this.openStream(id);
            if (part === 'clarifications' && method === 'POST') {
                this.clarificationAnswers.push((body as { answers: unknown }).answers);
                return json(200, { items: [] });
            }
        }
        const scans = /^\/api\/v1\/projects\/[^/]+\/scans$/.exec(path);
        if (scans && method === 'GET')
            return json(200, {
                items: this.overview ? [this.overview.scan] : [],
                page: 0,
                size: 20,
                totalElements: this.overview ? 1 : 0,
            });
        const scan = /^\/api\/v1\/scans\/([^/]+)(\/topology)?$/.exec(path);
        if (scan && method === 'GET') {
            if (!this.overview || this.overview.scan.id !== scan[1]) return problem(404, 'not-found');
            if (!scan[2]) return json(200, this.overview.summary);
            return this.overview.topology ? json(200, this.overview.topology) : problem(404, 'not-found');
        }
        return null;
    }

    find(method: string, pathPart: string): Call[] {
        return this.calls.filter((call) => call.method === method && call.url.pathname.includes(pathPart));
    }
}

export function activeConsent(type: Consent['consentType'], version = 1): Consent {
    return {
        consentType: type,
        privacyNoticeVersion: 2,
        grantedAt: '2026-10-19T11:00:00Z',
        revokedAt: null,
        version,
    };
}
