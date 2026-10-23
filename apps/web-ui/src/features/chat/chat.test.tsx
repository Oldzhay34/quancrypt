import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { ChatMessage, ClarificationQuestion, Scan } from '@/shared/api/types';
import { FakeBackend, PROJECT, SESSION_ID, activeConsent, sse } from '@/test/fakeBackend';
import type { ScanOverview } from '@/test/fakeBackend';
import { renderApp } from '@/test/renderApp';
import { REFUSAL_TEXTS } from './refusal';

const QUESTION = 'Servisler arasında RSA nerede?';
const SESSION_KEY = `chatSession:${PROJECT.id}`;

function openChat(backend: FakeBackend) {
    backend.consents = [activeConsent('MODEL_TRAINING')];
    return renderApp(backend, { path: '/chat' });
}

const message = (id: number, role: ChatMessage['role'], content: string, extra: Partial<ChatMessage> = {}) =>
    ({
        id: `00000000-0000-4000-8000-${String(id).padStart(12, '0')}`,
        role,
        content,
        created_at: '2026-10-24T10:00:00Z',
        ...extra,
    }) satisfies ChatMessage;

const done = (id = 'm-1') => sse('done', { message_id: id, llm_disabled: false });

async function typeAndSend(user: ReturnType<typeof userEvent.setup>, text: string) {
    await user.type(await screen.findByRole('textbox', { name: 'Mesajınız' }), `${text}{Enter}`);
}

const log = () => screen.getByRole('log', { name: 'Konuşma' });
const findLog = () => screen.findByRole('log', { name: 'Konuşma' });

describe('chat: sending a question', () => {
    it('streams the answer piece by piece with the keyboard, shows chips, and loads the stored answer afterwards', async () => {
        const backend = new FakeBackend();
        const handle = backend.queueStream({
            stored: [
                message(1, 'user', QUESTION),
                message(2, 'assistant', 'Merhaba dünya', {
                    evidence: [{ kind: 'code_location', reference: 'Pay.java:12', source_version: null }],
                }),
            ],
        });
        const user = userEvent.setup();
        openChat(backend);

        expect(screen.getByRole('button', { name: 'Durdur' })).toBeDisabled();
        await typeAndSend(user, QUESTION);

        // The session is created on the first message and remembered for the project.
        await waitFor(() => expect(backend.find('POST', '/messages')).toHaveLength(1));
        const created = backend.find('POST', '/api/v1/sessions')[0];
        expect(created?.body).toEqual({ project_id: PROJECT.id, language: 'tr' });
        expect(created?.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
        const sent = backend.find('POST', '/messages')[0];
        expect(sent?.url.origin).toBe('http://127.0.0.1:8083');
        expect(sent?.body).toEqual({ content: QUESTION });
        expect(sent?.headers.get('Accept')).toBe('text/event-stream');
        expect(window.localStorage.getItem(SESSION_KEY)).toMatch(/^[0-9a-f-]{36}$/);

        // While it streams: the log is busy, Stop is enabled, the question is shown, sending waits.
        await waitFor(() => expect(log()).toHaveAttribute('aria-busy', 'true'));
        expect(screen.getByRole('button', { name: 'Durdur' })).toBeEnabled();
        expect(log()).toHaveAttribute('aria-live', 'polite');
        expect(within(log()).getByText(QUESTION)).toBeInTheDocument();

        handle.push(sse('token', { text: 'Mer' }));
        handle.push(sse('token', { text: 'haba' }));
        expect(await within(log()).findByText('Merhaba')).toBeInTheDocument();
        handle.push(sse('token', { text: ' dünya' }));
        expect(await within(log()).findByText('Merhaba dünya')).toBeInTheDocument();

        handle.push(
            sse('evidence', {
                evidence: { kind: 'code_location', reference: 'Pay.java:12', source_version: null },
            }),
        );
        handle.push(
            sse('evidence', {
                evidence: {
                    kind: 'knowledge_base',
                    reference: 'https://openjdk.org/jeps/496',
                    source_version: 'JEP 496',
                    title: 'ML-KEM in the JDK',
                },
            }),
        );
        handle.push(
            sse('evidence', {
                evidence: { kind: 'knowledge_base', reference: 'javascript:alert(1)', source_version: null },
            }),
        );
        const link = await screen.findByRole('link', { name: 'ML-KEM in the JDK' });
        expect(link).toHaveAttribute('href', 'https://openjdk.org/jeps/496');
        expect(link).toHaveAttribute('rel', 'noopener noreferrer');
        expect(link).toHaveAttribute('target', '_blank');
        expect(screen.getByText('sürüm JEP 496')).toBeInTheDocument();
        expect(screen.getByText('Pay.java:12')).toBeInTheDocument();
        expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument();
        expect(within(log()).getAllByRole('link')).toHaveLength(1);

        handle.push(done());
        handle.close();

        // The turn ends: the stored history replaces the live copy, nothing is shown twice.
        await waitFor(() => expect(log()).toHaveAttribute('aria-busy', 'false'));
        await waitFor(() => expect(backend.find('GET', '/messages').length).toBeGreaterThan(0));
        await waitFor(() => expect(within(log()).getAllByText('Merhaba dünya')).toHaveLength(1));
        expect(within(log()).getAllByText(QUESTION)).toHaveLength(1);
        expect(within(log()).getByText('Pay.java:12')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Durdur' })).toBeDisabled();
        expect(screen.getByRole('button', { name: 'Gönder' })).toBeDisabled();
    });

    it('marks the claims the service could not verify and keeps shown text as plain text', async () => {
        const backend = new FakeBackend();
        const answer = '<b>RSA</b> kullanılıyor [doğrulanamadı]. Tamam.';
        backend.queueStream({
            text:
                sse('token', { text: '<b>RSA</b> kullanılıyor [doğrulanamadı].' }) +
                sse('token', { text: ' Tamam.' }) +
                done(),
            stored: [message(1, 'user', QUESTION), message(2, 'assistant', answer)],
        });
        const user = userEvent.setup();
        const { container } = openChat(backend);

        await typeAndSend(user, QUESTION);

        const mark = await waitFor(() => {
            const found = container.querySelector('mark');
            expect(found).not.toBeNull();
            return found as HTMLElement;
        });
        expect(mark).toHaveTextContent('[doğrulanamadı]');
        expect(screen.getByText('İşaretli iddialar araç çıktılarıyla doğrulanamadı.')).toBeInTheDocument();
        expect(container.querySelector('b')).toBeNull();
        expect(screen.getByText(/<b>RSA<\/b> kullanılıyor/)).toBeInTheDocument();
    });

    it('does not send on Shift+Enter, nor an empty message', async () => {
        const backend = new FakeBackend();
        const user = userEvent.setup();
        openChat(backend);

        const box = await screen.findByRole('textbox', { name: 'Mesajınız' });
        expect(screen.getByRole('button', { name: 'Gönder' })).toBeDisabled();
        await user.type(box, 'ilk{Shift>}{Enter}{/Shift}ikinci');
        expect(box).toHaveValue('ilk\nikinci');
        await user.clear(box);
        await user.type(box, '   {Enter}');
        expect(backend.find('POST', '/api/v1/sessions')).toHaveLength(0);
    });

    it('shows an out-of-scope request as a refusal card with the fixed sentence', async () => {
        const backend = new FakeBackend();
        const refusal = REFUSAL_TEXTS[0] as string;
        backend.queueStream({
            text: sse('refusal', { message: refusal }),
            stored: [message(1, 'user', 'Bana hava durumunu söyle'), message(2, 'assistant', refusal)],
        });
        const user = userEvent.setup();
        openChat(backend);

        await typeAndSend(user, 'Bana hava durumunu söyle');

        const card = await screen.findByRole('note');
        expect(card).toHaveTextContent('Kapsam dışı istek');
        expect(card).toHaveTextContent(refusal);
        // After the history is reloaded it is still a refusal card (recognised by its fixed sentence), shown once.
        await waitFor(() => expect(backend.find('GET', '/messages').length).toBeGreaterThan(0));
        await waitFor(() => expect(screen.getAllByRole('note')).toHaveLength(1));
        expect(screen.getAllByText(refusal)).toHaveLength(1);
    });

    it('tells a busy session apart: a second request while one runs gets a clear message', async () => {
        const backend = new FakeBackend();
        backend.failStream = { status: 409, code: 'session-busy' };
        const user = userEvent.setup();
        openChat(backend);

        await typeAndSend(user, QUESTION);

        expect(await screen.findByRole('alert')).toHaveTextContent('Oturumda önceki bir yanıt sürüyor');
        // The question stays visible, the box is usable again.
        expect(within(log()).getByText(QUESTION)).toBeInTheDocument();
        expect(screen.getByRole('textbox', { name: 'Mesajınız' })).toBeEnabled();
    });
});

describe('chat: stop', () => {
    it('stops exactly the running session from the header, keeps the partial text and says so', async () => {
        const backend = new FakeBackend();
        const handle = backend.queueStream({ stored: [message(1, 'user', QUESTION)] });
        const user = userEvent.setup();
        openChat(backend);

        await typeAndSend(user, QUESTION);
        handle.push(sse('token', { text: 'yarım kalan' }));
        await within(log()).findByText('yarım kalan');
        const stop = screen.getByRole('button', { name: 'Durdur' });
        await waitFor(() => expect(stop).toBeEnabled());
        await user.click(stop);

        const sessionId = window.localStorage.getItem(SESSION_KEY);
        await waitFor(() => expect(backend.find('POST', '/stop')).toHaveLength(1));
        const call = backend.find('POST', '/stop')[0];
        expect(call?.url.pathname).toBe(`/api/v1/sessions/${sessionId}/stop`);
        expect(call?.headers.get('Authorization')).toMatch(/^Bearer /);

        // The service ends the stream with the "stopped" error.
        handle.push(sse('error', { code: 'stopped' }));
        handle.close();
        expect(
            await screen.findByText('Yanıt durduruldu. Gelen kısmi metin yukarıda kalır.'),
        ).toBeInTheDocument();
        expect(within(log()).getByText('yarım kalan')).toBeInTheDocument();
        await waitFor(() => expect(log()).toHaveAttribute('aria-busy', 'false'));
        expect(screen.getByRole('textbox', { name: 'Mesajınız' })).toBeEnabled();
    });

    it('reports a failed stream with its own message', async () => {
        const backend = new FakeBackend();
        backend.queueStream({
            text: sse('token', { text: 'a' }) + sse('error', { code: 'llm_unavailable' }),
        });
        const user = userEvent.setup();
        openChat(backend);

        await typeAndSend(user, QUESTION);

        expect(await screen.findByRole('alert')).toHaveTextContent('Dil modeline ulaşılamadı');
    });

    it('reports a stream that ends without a final event as incomplete', async () => {
        const backend = new FakeBackend();
        backend.queueStream({ text: sse('token', { text: 'yarım' }) });
        const user = userEvent.setup();
        openChat(backend);

        await typeAndSend(user, QUESTION);

        expect(await screen.findByRole('alert')).toHaveTextContent('beklenmeyen bir akış');
        expect(within(log()).getByText('yarım')).toBeInTheDocument();
    });
});

describe('chat: history', () => {
    it('loads the stored conversation of the remembered session, evidence and refusal included', async () => {
        const backend = new FakeBackend();
        backend.addSession([
            message(1, 'user', QUESTION),
            message(2, 'assistant', 'RSA burada kullanılıyor.', {
                evidence: [
                    { kind: 'code_location', reference: 'Token.java:8', source_version: null },
                    {
                        kind: 'knowledge_base',
                        reference: 'https://csrc.nist.gov/pubs/fips/203/final',
                        source_version: 'FIPS 203',
                    },
                ],
            }),
            message(3, 'user', 'Bana hava durumunu söyle'),
            message(4, 'assistant', REFUSAL_TEXTS[1] as string),
        ]);
        window.localStorage.setItem(SESSION_KEY, SESSION_ID);
        openChat(backend);

        await findLog();
        expect(await within(log()).findByText('RSA burada kullanılıyor.')).toBeInTheDocument();
        expect(within(log()).getByText('Token.java:8')).toBeInTheDocument();
        // A stored knowledge-base entry has no title: the link shows host and path.
        expect(
            within(log()).getByRole('link', { name: 'csrc.nist.gov/pubs/fips/203/final' }),
        ).toHaveAttribute('href', 'https://csrc.nist.gov/pubs/fips/203/final');
        expect(within(log()).getByRole('note')).toHaveTextContent(REFUSAL_TEXTS[1] as string);
        expect(backend.find('POST', '/api/v1/sessions')).toHaveLength(0);
    });

    it('forgets a remembered session the service no longer knows', async () => {
        const backend = new FakeBackend();
        window.localStorage.setItem(SESSION_KEY, SESSION_ID);
        openChat(backend);

        await waitFor(() => expect(window.localStorage.getItem(SESSION_KEY)).toBeNull());
        expect(await screen.findByText(/Henüz mesaj yok/)).toBeInTheDocument();
        expect(screen.queryByRole('alert')).toBeNull();
    });

    it('deletes the history only after the user confirms, and forgets the session', async () => {
        const backend = new FakeBackend();
        backend.addSession([message(1, 'user', QUESTION), message(2, 'assistant', 'Yanıt')]);
        window.localStorage.setItem(SESSION_KEY, SESSION_ID);
        const user = userEvent.setup();
        openChat(backend);
        await findLog();
        await within(log()).findByText('Yanıt');

        await user.click(screen.getByRole('button', { name: 'Geçmişi sil' }));
        const dialog = screen.getByRole('dialog', { name: 'Sohbet geçmişi silinsin mi?' });
        expect(backend.find('DELETE', '/api/v1/sessions')).toHaveLength(0);

        await user.click(within(dialog).getByRole('button', { name: 'Vazgeç' }));
        expect(screen.queryByRole('dialog')).toBeNull();
        expect(backend.find('DELETE', '/api/v1/sessions')).toHaveLength(0);

        await user.click(screen.getByRole('button', { name: 'Geçmişi sil' }));
        await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Geçmişi sil' }));

        await waitFor(() => expect(backend.find('DELETE', '/api/v1/sessions')).toHaveLength(1));
        expect(backend.find('DELETE', '/api/v1/sessions')[0]?.url.pathname).toBe(
            `/api/v1/sessions/${SESSION_ID}`,
        );
        await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
        expect(window.localStorage.getItem(SESSION_KEY)).toBeNull();
        expect(await screen.findByText(/Henüz mesaj yok/)).toBeInTheDocument();
        expect(screen.queryByText('Yanıt')).toBeNull();
        expect(screen.getByRole('button', { name: 'Geçmişi sil' })).toBeDisabled();
    });
});

const QUESTIONS: ClarificationQuestion[] = [
    {
        question_code: 'TLS_TERMINATION',
        text: { tr: 'TLS nerede sonlanıyor?', en: 'Where does TLS terminate?' },
        options: [
            { option_code: 'APPLICATION', text: { tr: 'APPLICATION', en: 'APPLICATION' } },
            { option_code: 'UNKNOWN', text: { tr: 'UNKNOWN', en: 'UNKNOWN' } },
        ],
        answer_kind: 'OPTION',
        answer: null,
    },
    {
        question_code: 'COMPLIANCE_REQUIREMENT',
        text: { tr: 'Uyum gereksinimi var mı?', en: 'Is there a compliance requirement?' },
        options: [
            { option_code: 'YES', text: { tr: 'YES', en: 'YES' } },
            { option_code: 'NO', text: { tr: 'NO', en: 'NO' } },
        ],
        answer_kind: 'OPTION_WITH_TEXT',
        answer: null,
    },
    {
        question_code: 'DEVICE_HARDWARE_OPENSSL',
        text: { tr: 'Cihazdaki OpenSSL sürümü?', en: 'OpenSSL version on the device?' },
        options: [],
        answer_kind: 'TEXT',
        answer: null,
    },
];

describe('chat: clarification form', () => {
    it('asks the questions, validates, saves the answers and sends the original question again', async () => {
        const backend = new FakeBackend();
        const PLAN_QUESTION = 'Hangi bulguları önce düzeltmeliyim?';
        const first = backend.queueStream({ stored: [message(1, 'user', PLAN_QUESTION)] });
        backend.queueStream({
            stored: [message(3, 'user', PLAN_QUESTION), message(4, 'assistant', 'Önce P0 bulguları.')],
            text: sse('token', { text: 'Önce P0 bulguları.' }) + done('m-2'),
        });
        const user = userEvent.setup();
        openChat(backend);

        await typeAndSend(user, PLAN_QUESTION);
        first.push(sse('clarification_required', { questions: QUESTIONS }));

        // While the first answer still streams, saving waits.
        const submit = await screen.findByRole('button', { name: 'Yanıtları kaydet ve planı sürdür' });
        expect(submit).toBeDisabled();
        expect(screen.getByText('Yanıt akışı bitince gönderebilirsiniz.')).toBeInTheDocument();
        first.push(done());
        first.close();
        await waitFor(() => expect(submit).toBeEnabled());

        // Nothing answered: every question asks for an answer and nothing is sent.
        await user.click(submit);
        expect(await screen.findAllByText('Bu soruyu yanıtlayın.')).toHaveLength(3);
        expect(backend.clarificationAnswers).toHaveLength(0);
        expect(backend.find('POST', '/clarifications')).toHaveLength(0);

        // Answer everything: options by code, optional text with an option, required text for the device.
        await user.click(screen.getByRole('radio', { name: 'Uygulama' }));
        await user.click(screen.getByRole('radio', { name: 'Evet' }));
        const description = screen.getByLabelText('Açıklama', { selector: 'textarea' });
        await user.type(description, 'OpenSSL 3.0.13');
        await user.type(screen.getByLabelText('Açıklama (isteğe bağlı)'), 'FIPS 140-3');
        await user.click(submit);

        await waitFor(() => expect(backend.clarificationAnswers).toHaveLength(1));
        expect(backend.clarificationAnswers[0]).toEqual([
            { question_code: 'TLS_TERMINATION', option_code: 'APPLICATION', free_text: null },
            { question_code: 'COMPLIANCE_REQUIREMENT', option_code: 'YES', free_text: 'FIPS 140-3' },
            { question_code: 'DEVICE_HARDWARE_OPENSSL', option_code: null, free_text: 'OpenSSL 3.0.13' },
        ]);
        expect(backend.find('POST', '/clarifications')[0]?.headers.get('Idempotency-Key')).toMatch(
            /^[0-9a-f-]{36}$/,
        );

        // The original question goes out a second time and the plan answer streams in.
        await waitFor(() => expect(backend.find('POST', '/messages')).toHaveLength(2));
        expect(backend.find('POST', '/messages')[1]?.body).toEqual({ content: PLAN_QUESTION });
        expect(await within(log()).findByText('Önce P0 bulguları.')).toBeInTheDocument();
        await waitFor(() =>
            expect(screen.queryByRole('button', { name: 'Yanıtları kaydet ve planı sürdür' })).toBeNull(),
        );
        await waitFor(() => expect(within(log()).getAllByText(PLAN_QUESTION)).toHaveLength(2));
    });

    it('limits a description to 500 characters and sends a text answer without an option', async () => {
        const backend = new FakeBackend();
        const handle = backend.queueStream({});
        const user = userEvent.setup();
        openChat(backend);
        await typeAndSend(user, 'Planı çıkar');
        handle.push(sse('clarification_required', { questions: [QUESTIONS[2]] }));
        handle.push(done());
        handle.close();

        const box = await screen.findByLabelText('Açıklama');
        // The box stops typing at 500 characters; a pasted longer text is cut by the browser the same way.
        expect(box).toHaveAttribute('maxlength', '500');
        await user.type(box, 'x');
        await user.click(screen.getByRole('button', { name: 'Yanıtları kaydet ve planı sürdür' }));
        await waitFor(() => expect(backend.clarificationAnswers).toHaveLength(1));
        expect(backend.clarificationAnswers[0]).toEqual([
            { question_code: 'DEVICE_HARDWARE_OPENSSL', option_code: null, free_text: 'x' },
        ]);
    });
});

describe('chat: initial scan', () => {
    const SCAN: Scan = {
        id: '33333333-3333-4333-8333-333333333333',
        projectId: PROJECT.id,
        status: 'COMPLETED',
        startedAt: '2026-10-24T10:00:00Z',
        completedAt: '2026-10-24T10:02:00Z',
        runtimeProfileSequenceNo: null,
    };
    const overview = (topology: ScanOverview['topology']): ScanOverview => ({
        scan: SCAN,
        summary: {
            scan: SCAN,
            runtimeProfile: null,
            findingCount: 28,
            countsByPriority: { P0: 3, P1: 9, P3: 16 },
            countsByAlgorithmFamily: { RSA: 20, UNKNOWN: 5, SHA1: 3 },
            countsByLocationKind: { CODE: 28 },
        },
        topology,
    });

    it('says the project was not scanned yet, checks the root, and shows the summary after the scan', async () => {
        const backend = new FakeBackend();
        const scanTopology = {
            scanId: SCAN.id,
            recordedAt: '2026-10-24T10:02:00Z',
            nodes: [
                { name: 'qbank-gateway', nodeKind: 'GATEWAY' as const },
                { name: 'qbank-payment-service', nodeKind: 'SERVICE' as const },
                { name: 'qbank-account-service', nodeKind: 'SERVICE' as const },
            ],
            links: [
                {
                    source: 'qbank-gateway',
                    target: 'qbank-payment-service',
                    protocol: 'HTTP' as const,
                    tls: true,
                    mtls: true,
                    callSites: [],
                    findingIds: [],
                },
                {
                    source: 'qbank-payment-service',
                    target: 'qbank-account-service',
                    protocol: 'HTTP' as const,
                    tls: true,
                    mtls: true,
                    callSites: [],
                    findingIds: [],
                },
            ],
        };
        backend.queueStream({
            text: done('scan'),
            onClose: () => {
                backend.overview = overview(scanTopology);
            },
        });
        const user = userEvent.setup();
        openChat(backend);

        expect(await screen.findByText('Bu proje henüz taranmadı.')).toBeInTheDocument();
        const root = screen.getByRole('textbox', { name: 'Analiz kökü' });
        expect(root).toHaveValue('/workspace');

        // A root outside /workspace and /corpus is explained and nothing is sent.
        await user.clear(root);
        await user.type(root, '/etc/passwd');
        await user.click(screen.getByRole('button', { name: 'İlk taramayı başlat' }));
        expect(await screen.findByRole('alert')).toHaveTextContent('Kök /workspace veya /corpus');
        expect(backend.find('POST', '/api/v1/sessions')).toHaveLength(0);

        await user.clear(root);
        await user.type(root, '/workspace/qbank-payment-service');
        await user.click(screen.getByRole('button', { name: 'İlk taramayı başlat' }));

        await waitFor(() => expect(backend.find('POST', '/initial-scan')).toHaveLength(1));
        expect(backend.find('POST', '/initial-scan')[0]?.body).toEqual({
            root: '/workspace/qbank-payment-service',
        });

        const summary = await screen.findByRole('region', { name: 'Tarama özeti' });
        expect(within(summary).getByText('Toplam bulgu: 28')).toBeInTheDocument();
        expect(within(summary).getByText('Servis düğümü: 3')).toBeInTheDocument();
        expect(within(summary).getByText('Bağlantı (kenar): 2')).toBeInTheDocument();
        const families = within(summary).getByRole('table', { name: 'Algoritma ailesine göre' });
        expect(
            within(within(families).getByRole('row', { name: /RSA/ })).getByText('20'),
        ).toBeInTheDocument();
        const priorities = within(summary).getByRole('table', { name: 'Önceliğe göre' });
        expect(
            within(within(priorities).getByRole('row', { name: /P0/ })).getByText('3'),
        ).toBeInTheDocument();
        // A priority without findings shows 0.
        expect(
            within(within(priorities).getByRole('row', { name: /P2/ })).getByText('0'),
        ).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Yeniden tara' })).toBeInTheDocument();
    });

    it('shows the latest scan when the chat opens, and says so when its topology was not recorded', async () => {
        const backend = new FakeBackend();
        backend.overview = overview(null);
        openChat(backend);

        const summary = await screen.findByRole('region', { name: 'Tarama özeti' });
        expect(within(summary).getByText('Toplam bulgu: 28')).toBeInTheDocument();
        expect(within(summary).getByText('Topoloji kaydedilmedi.')).toBeInTheDocument();
    });

    it('shows the running state while the scan streams and blocks a second start', async () => {
        const backend = new FakeBackend();
        const handle = backend.queueStream({});
        const user = userEvent.setup();
        openChat(backend);

        await user.click(await screen.findByRole('button', { name: 'İlk taramayı başlat' }));

        // The running note shows in the scan panel and in the conversation.
        expect(await screen.findAllByText('Tarama sürüyor. Bu birkaç dakika sürebilir…')).toHaveLength(2);
        expect(screen.getByRole('button', { name: 'İlk taramayı başlat' })).toBeDisabled();
        expect(screen.getByRole('button', { name: 'Durdur' })).toBeEnabled();

        handle.push(done('scan'));
        handle.close();
        await waitFor(() =>
            expect(screen.queryByText('Tarama sürüyor. Bu birkaç dakika sürebilir…')).toBeNull(),
        );
    });
});
