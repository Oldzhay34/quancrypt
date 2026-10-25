import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/renderApp';
import { captureDownloads, reviewBackend } from '@/test/review';
import { PLAN_ITEMS, REPORT_TR } from '@/test/reviewFixtures';

afterEach(() => vi.restoreAllMocks());

const bodyRows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1);

describe('plan screen: items', () => {
    it('lists the items by risk, highest first, with priority, strategy, effort, risk class and state badge', async () => {
        renderApp(reviewBackend(), { path: '/plan' });

        await screen.findByRole('table');
        const rows = bodyRows();
        expect(rows).toHaveLength(3);
        const paths = rows.map((row) => within(row).getAllByRole('cell')[1]?.textContent ?? '');
        expect(paths[0]).toContain('src/main/java/Pay3.java:13');
        expect(paths[1]).toContain('src/main/java/Pay1.java:11');
        expect(paths[2]).toContain('src/main/java/Pay2.java');

        const first = within(rows[0] as HTMLElement);
        expect(first.getByText('P0')).toBeInTheDocument();
        expect(first.getByText('FIX_WEAK_CLASSIC')).toBeInTheDocument();
        expect(first.getByText('CRITICAL')).toBeInTheDocument();
        expect(first.getByText('0.90')).toBeInTheDocument();
        expect(first.getByText('Planlandı')).toBeInTheDocument();
        expect(within(rows[2] as HTMLElement).getByText('Onaylandı')).toBeInTheDocument();
    });

    it('shows the SHAP reasons of an item, and says plainly when a rule-based score has none', async () => {
        const user = userEvent.setup();
        renderApp(reviewBackend(), { path: '/plan' });
        await screen.findByRole('table');
        const rows = bodyRows();

        await user.click(within(rows[0] as HTMLElement).getByText('2 gerekçe'));
        expect(within(rows[0] as HTMLElement).getByText('weak_hash: 0.312')).toBeInTheDocument();
        expect(within(rows[0] as HTMLElement).getByText('on_service_path: 0.100')).toBeInTheDocument();
        expect(
            within(rows[1] as HTMLElement).getByText('Gerekçe yok (kural tabanlı skor)'),
        ).toBeInTheDocument();
    });

    it('offers "Onayla" only for planned items', async () => {
        renderApp(reviewBackend(), { path: '/plan' });
        await screen.findByRole('table');

        expect(screen.getAllByRole('button', { name: 'Onayla' })).toHaveLength(2);
        const approved = within(bodyRows()[2] as HTMLElement);
        expect(approved.queryByRole('button', { name: 'Onayla' })).toBeNull();
    });

    it('approves an item after confirmation: only the state changes, with the version in If-Match', async () => {
        const backend = reviewBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/plan' });
        await screen.findByRole('table');

        await user.click(within(bodyRows()[0] as HTMLElement).getByRole('button', { name: 'Onayla' }));
        const dialog = screen.getByRole('dialog', { name: 'Madde onaylansın mı?' });
        expect(within(dialog).getByText(/Kodda hiçbir değişiklik yapılmaz/)).toBeInTheDocument();
        expect(backend.find('POST', '/transitions')).toHaveLength(0);
        await user.click(within(dialog).getByRole('button', { name: 'Onayla' }));

        await waitFor(() => expect(backend.find('POST', '/transitions')).toHaveLength(1));
        const call = backend.find('POST', '/transitions')[0];
        expect(call?.url.pathname).toBe(`/api/v1/plan-items/${PLAN_ITEMS[1]?.id}/transitions`);
        expect(call?.body).toEqual({ toState: 'APPROVED' });
        expect(call?.headers.get('If-Match')).toBe('"1"');
        expect(call?.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
        await waitFor(() =>
            expect(within(bodyRows()[0] as HTMLElement).getByText('Onaylandı')).toBeInTheDocument(),
        );
        expect(screen.getAllByRole('button', { name: 'Onayla' })).toHaveLength(1);
    });

    it('does nothing when the confirmation is cancelled', async () => {
        const backend = reviewBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/plan' });
        await screen.findByRole('table');

        await user.click(within(bodyRows()[0] as HTMLElement).getByRole('button', { name: 'Onayla' }));
        await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Vazgeç' }));

        expect(screen.queryByRole('dialog')).toBeNull();
        expect(backend.find('POST', '/transitions')).toHaveLength(0);
    });

    it('explains a conflict and a refused transition, and reads the plan again', async () => {
        const backend = reviewBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/plan' });
        await screen.findByRole('table');
        const planReads = () =>
            backend.find('GET', '/plan').filter((call) => call.url.pathname.endsWith('/plan'));
        const before = planReads().length;
        backend.failTransition = { status: 409, code: 'concurrent-modification' };

        await user.click(within(bodyRows()[0] as HTMLElement).getByRole('button', { name: 'Onayla' }));
        await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Onayla' }));

        expect(await screen.findByRole('alert')).toHaveTextContent('başka bir yerden değiştirilmiş');
        await waitFor(() => expect(planReads().length).toBeGreaterThan(before));

        backend.failTransition = { status: 409, code: 'invalid-state-transition' };
        await user.click(within(bodyRows()[0] as HTMLElement).getByRole('button', { name: 'Onayla' }));
        await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Onayla' }));
        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('izin verilmiyor'));
    });

    it('says there is no plan yet, on both tabs', async () => {
        const backend = reviewBackend();
        backend.plan = null;
        backend.planReport = null;
        const user = userEvent.setup();
        renderApp(backend, { path: '/plan' });

        expect(await screen.findByText(/Bu tarama için plan yok/)).toBeInTheDocument();
        await user.click(screen.getByRole('tab', { name: 'Rapor' }));
        expect(await screen.findByText(/Bu tarama için plan yok/)).toBeInTheDocument();
    });
});

describe('plan screen: report', () => {
    async function openReport(backend = reviewBackend()) {
        const user = userEvent.setup();
        const view = renderApp(backend, { path: '/plan' });
        await user.click(await screen.findByRole('tab', { name: 'Rapor' }));
        await screen.findByRole('heading', { name: 'Quancrypt geçiş planı raporu' });
        return { user, backend, view };
    }

    it('renders the Markdown report of the service as a document', async () => {
        const { backend } = await openReport();

        expect(screen.getByRole('heading', { name: '2. Maddeler (riske göre sıralı)' })).toBeInTheDocument();
        expect(
            screen.getByRole('heading', { name: '3.1. src/main/java/Pay3.java — Pay3#sign' }),
        ).toBeInTheDocument();
        const table = screen.getByRole('table');
        expect(within(table).getAllByRole('row')).toHaveLength(3);
        // The service's backslash escapes are taken back: the file name reads as it is.
        expect(within(table).getByText('src/a|b.java')).toBeInTheDocument();
        expect(within(table).getByText('Pay1_x')).toBeInTheDocument();
        expect(screen.getByText('1. Özet')).toBeInTheDocument();
        expect(screen.getByText('weak_hash: 0.312340')).toBeInTheDocument();
        const call = backend.find('GET', '/plan/report')[0];
        expect(call?.headers.get('Accept-Language')).toBe('tr');
        expect(call?.headers.get('Accept')).toBe('text/markdown');
    });

    it('shows markup in the report as text, never as HTML', async () => {
        const { view } = await openReport();

        expect(view.container.querySelector('script')).toBeNull();
        expect(screen.getByText('<script>alert(1)</script> düz metin')).toBeInTheDocument();
    });

    it('asks for the report in the interface language', async () => {
        const user = userEvent.setup();
        const backend = reviewBackend();
        renderApp(backend, { path: '/plan' });
        await user.click(await screen.findByRole('tab', { name: 'Rapor' }));
        await screen.findByRole('heading', { name: 'Quancrypt geçiş planı raporu' });

        await user.selectOptions(screen.getByLabelText('Dil'), 'en');

        expect(
            await screen.findByRole('heading', { name: 'Quancrypt migration plan report' }),
        ).toBeInTheDocument();
        expect(backend.find('GET', '/plan/report').at(-1)?.headers.get('Accept-Language')).toBe('en');
        expect(screen.getByText('Total items: 3')).toBeInTheDocument();
    });

    it('saves the Markdown exactly as the service wrote it', async () => {
        const downloads = captureDownloads();
        const { user } = await openReport();

        await user.click(screen.getByRole('button', { name: 'Markdown indir' }));

        expect(downloads.names).toEqual(['quancrypt-plan-33333333-tr.md']);
        expect(await downloads.blobs[0]?.text()).toBe(REPORT_TR);
        expect(downloads.blobs[0]?.type).toContain('text/markdown');
    });

    it('opens the print dialog of the browser, from which the report is saved as PDF', async () => {
        const print = vi.fn();
        vi.stubGlobal('print', print);
        const { user } = await openReport();

        await user.click(screen.getByRole('button', { name: 'Yazdır / PDF' }));

        expect(print).toHaveBeenCalledTimes(1);
        vi.unstubAllGlobals();
    });
});
