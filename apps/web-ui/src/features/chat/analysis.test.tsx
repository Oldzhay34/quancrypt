import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import type { Finding, Scan } from '@/shared/api/types';
import { FakeBackend, PROJECT, activeConsent } from '@/test/fakeBackend';
import type { ScanOverview } from '@/test/fakeBackend';
import { renderApp } from '@/test/renderApp';

const SCAN: Scan = {
    id: '33333333-3333-4333-8333-333333333333',
    projectId: PROJECT.id,
    status: 'COMPLETED',
    startedAt: '2026-10-24T10:00:00Z',
    completedAt: '2026-10-24T10:02:00Z',
    runtimeProfileSequenceNo: null,
};
const OVERVIEW: ScanOverview = {
    scan: SCAN,
    summary: {
        scan: SCAN,
        runtimeProfile: null,
        findingCount: 2,
        countsByPriority: { P0: 1, P3: 1 },
        countsByAlgorithmFamily: { RSA: 2 },
        countsByLocationKind: { CODE: 2 },
    },
    topology: null,
};
const finding = (n: number, over: Partial<Finding> = {}): Finding => ({
    id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
    scanId: SCAN.id,
    path: `src/File${n}.java`,
    symbol: `File${n}#run`,
    algorithmFamily: 'RSA',
    usageContext: 'ENCRYPTION',
    locationKind: 'CODE',
    priority: 'P3',
    keySizeBits: 2048,
    lineStart: 10,
    lineEnd: 10,
    confidence: 0.9,
    classifiedBy: 'STATIC',
    ...over,
});

function open(backend: FakeBackend) {
    backend.consents = [activeConsent('MODEL_TRAINING')];
    backend.overview = OVERVIEW;
    return renderApp(backend, { path: '/analysis' });
}
const snippetCalls = (backend: FakeBackend) => backend.find('GET', '/api/v1/snippet');
const roots = (backend: FakeBackend) =>
    snippetCalls(backend).map((call) => call.url.searchParams.get('root'));

describe('analysis: findings with their code (D-361c)', () => {
    beforeEach(() => window.localStorage.clear());

    it('lists the most urgent finding first with its place and the marked lines, and asks with the root', async () => {
        const backend = new FakeBackend();
        backend.findings = [finding(1), finding(2, { priority: 'P0', lineStart: 7, lineEnd: 7 })];
        window.localStorage.setItem(`quancrypt.scanRoot:${PROJECT.id}`, '/workspace/qbank-payment-service');
        open(backend);

        const headings = await screen.findAllByRole('heading', { level: 3, name: /src\/File/ });
        expect(headings.map((heading) => heading.textContent)).toEqual([
            'src/File2.java:7',
            'src/File1.java:10',
        ]);
        await waitFor(() => expect(screen.getAllByText('Java')).toHaveLength(2));
        expect(screen.getByRole('textbox', { name: 'Analiz kökü' })).toHaveValue(
            '/workspace/qbank-payment-service',
        );
        const asked = snippetCalls(backend)[0];
        expect(asked?.url.origin).toBe('http://127.0.0.1:8083');
        expect(asked?.headers.get('Authorization')).toMatch(/^Bearer /);
        expect(asked?.url.searchParams.get('context')).toBe('3');
        expect(asked?.url.searchParams.get('scan_id')).toBe(SCAN.id);
        expect(new Set(roots(backend))).toEqual(new Set(['/workspace/qbank-payment-service']));
    });

    it('never asks for a key store or a whole-file finding, and says when a file is withheld', async () => {
        const backend = new FakeBackend();
        backend.findings = [
            finding(1, { locationKind: 'KEYSTORE_FILE', path: 'certs/store.p12' }),
            finding(2, { lineStart: null, lineEnd: null, path: 'certs/ca.crt.pem' }),
            finding(3, { path: 'secret/File.java' }),
        ];
        backend.withheld = ['secret/File.java'];
        open(backend);

        expect(await screen.findByText(/dosya bu kök altında bulunamadı/)).toBeInTheDocument();
        expect(screen.getAllByText(/dosyanın tamamına aittir/)).toHaveLength(2);
        expect(snippetCalls(backend).map((call) => call.url.searchParams.get('path'))).toEqual([
            'secret/File.java',
        ]);
    });

    it('asks for code only for the ten findings it shows, and for more on demand', async () => {
        const backend = new FakeBackend();
        backend.findings = Array.from({ length: 13 }, (_, index) => finding(index + 1));
        const user = userEvent.setup();
        open(backend);

        await waitFor(() => expect(snippetCalls(backend)).toHaveLength(10));
        await user.click(screen.getByRole('button', { name: 'Daha fazla göster (3 bulgu kaldı)' }));
        await waitFor(() => expect(snippetCalls(backend)).toHaveLength(13));
    });

    it('reads the code again below a corrected root and remembers it, without starting a scan', async () => {
        const backend = new FakeBackend();
        backend.findings = [finding(1)];
        const user = userEvent.setup();
        open(backend);
        await waitFor(() => expect(roots(backend)).toEqual(['/workspace']));

        const box = screen.getByRole('textbox', { name: 'Analiz kökü' });
        await user.clear(box);
        await user.type(box, '/workspace/qbank-gateway');
        await user.click(screen.getByRole('button', { name: 'Bu kökle kodu göster' }));

        await waitFor(() => expect(roots(backend)).toEqual(['/workspace', '/workspace/qbank-gateway']));
        expect(window.localStorage.getItem(`quancrypt.scanRoot:${PROJECT.id}`)).toBe(
            '/workspace/qbank-gateway',
        );
        expect(backend.find('POST', '/initial-scan')).toHaveLength(0);
    });
});

describe('empty chat (D-361a)', () => {
    it('draws the quantum computer with the labels of the picture', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('MODEL_TRAINING')];
        renderApp(backend, { path: '/chat' });

        const drawing = await screen.findByRole('img', { name: /Kuantum bilgisayarın çizimi/ });
        for (const label of ['FPGA controller', '300 K', '50 K', '4 K', '100 mK', '10 mK', 'qubits']) {
            expect(within(drawing).getByText(label)).toBeInTheDocument();
        }
    });
});
