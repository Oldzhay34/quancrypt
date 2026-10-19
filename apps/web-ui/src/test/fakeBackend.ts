import type { Consent, Project } from '@/shared/api/types';

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

/** A stand-in for core-service and agent-service: records every call, answers from mutable state. */
export class FakeBackend {
    calls: Call[] = [];
    projects: Project[] = [PROJECT];
    consents: Consent[] = [];
    notice = NOTICE;
    unauthorized = false;
    failNext: number | null = null;

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
        return json(404, {}, 'application/problem+json');
    };

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
