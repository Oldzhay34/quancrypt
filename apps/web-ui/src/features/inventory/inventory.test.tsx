import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/renderApp';
import { captureDownloads, reviewBackend } from '@/test/review';
import { finding } from '@/test/reviewFixtures';

afterEach(() => vi.restoreAllMocks());

const dataRows = () => within(screen.getByRole('table')).getAllByRole('row').slice(1);
const findingCalls = (backend: ReturnType<typeof reviewBackend>) => backend.find('GET', '/findings');

describe('inventory screen', () => {
    it('shows the counts, then the findings of the newest scan with their codes and locations', async () => {
        const backend = reviewBackend();
        renderApp(backend, { path: '/inventory' });

        const table = await screen.findByRole('table');
        expect(within(table).getByText('Bulgular: 6')).toBeInTheDocument();
        expect(dataRows()).toHaveLength(6);
        const strip = await screen.findByRole('list', { name: 'Bulgu sayıları' });
        expect(within(strip).getByText('Toplam').nextSibling).toHaveTextContent('6');
        expect(within(strip).getByText('P0').nextSibling).toHaveTextContent('1');
        expect(within(strip).getByText('TEST_CODE').nextSibling).toHaveTextContent('1');
        // File and line are text; a finding without a line shows the file only.
        expect(within(table).getByText('src/main/java/Pay1.java:11')).toBeInTheDocument();
        expect(within(table).getByText('src/main/java/Pay2.java')).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: /Pay1/ })).toBeNull();
        expect(findingCalls(backend)[0]?.headers.get('Authorization')).toMatch(/^Bearer /);
    });

    it('asks the service for a priority and shows only those findings', async () => {
        const backend = reviewBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/inventory' });
        await screen.findByRole('table');

        await user.selectOptions(screen.getByLabelText('Öncelik'), 'P0');

        await waitFor(() => expect(dataRows()).toHaveLength(1));
        expect(within(screen.getByRole('table')).getByText('Bulgular: 1')).toBeInTheDocument();
        expect(findingCalls(backend).some((call) => call.url.searchParams.get('priority') === 'P0')).toBe(
            true,
        );
    });

    it('combines algorithm family, usage context and location kind', async () => {
        const backend = reviewBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/inventory' });
        await screen.findByRole('table');

        await user.selectOptions(screen.getByLabelText('Algoritma ailesi'), 'RSA');
        await waitFor(() => expect(dataRows()).toHaveLength(3));
        await user.selectOptions(screen.getByLabelText('Kullanım bağlamı'), 'CERTIFICATE');
        await waitFor(() => expect(dataRows()).toHaveLength(1));
        await user.selectOptions(screen.getByLabelText('Konum türü'), 'CERTIFICATE_FILE');
        await waitFor(() => expect(dataRows()).toHaveLength(1));

        const last = findingCalls(backend).at(-1)?.url.searchParams;
        expect(last?.get('algorithmFamily')).toBe('RSA');
        expect(last?.get('usageContext')).toBe('CERTIFICATE');
        expect(last?.get('locationKind')).toBe('CERTIFICATE_FILE');
    });

    it('leaves test code out, or shows only test code', async () => {
        const backend = reviewBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/inventory' });
        await screen.findByRole('table');

        await user.selectOptions(screen.getByLabelText('Test kodu'), 'exclude');
        await waitFor(() => expect(dataRows()).toHaveLength(5));
        expect(screen.queryByText('TEST_CODE', { selector: 'td' })).toBeNull();

        await user.selectOptions(screen.getByLabelText('Test kodu'), 'only');
        await waitFor(() => expect(dataRows()).toHaveLength(1));
        expect(screen.getByLabelText('Konum türü')).toBeDisabled();
        expect(findingCalls(backend).at(-1)?.url.searchParams.get('locationKind')).toBe('TEST_CODE');
    });

    it('says so when no finding matches', async () => {
        const backend = reviewBackend();
        const user = userEvent.setup();
        renderApp(backend, { path: '/inventory' });
        await screen.findByRole('table');

        await user.selectOptions(screen.getByLabelText('Algoritma ailesi'), 'MD5');

        expect(await screen.findByText('Bu filtreyle eşleşen bulgu yok.')).toBeInTheDocument();
        expect(screen.queryByRole('table')).toBeNull();
    });

    it('pages a long list, 25 rows at a time, and returns to the first page when the filter changes', async () => {
        const backend = reviewBackend();
        backend.findings = Array.from({ length: 60 }, (_, index) =>
            finding(100 + index, { priority: index % 2 === 0 ? 'P0' : 'P1' }),
        );
        const user = userEvent.setup();
        renderApp(backend, { path: '/inventory' });

        await screen.findByRole('table');
        expect(dataRows()).toHaveLength(25);
        expect(screen.getByText('Sayfa 1 / 3')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Önceki' })).toBeDisabled();

        await user.click(screen.getByRole('button', { name: 'Sonraki' }));
        await user.click(screen.getByRole('button', { name: 'Sonraki' }));
        expect(screen.getByText('Sayfa 3 / 3')).toBeInTheDocument();
        expect(dataRows()).toHaveLength(10);
        expect(screen.getByRole('button', { name: 'Sonraki' })).toBeDisabled();

        await user.selectOptions(screen.getByLabelText('Öncelik'), 'P0');
        await waitFor(() => expect(screen.getByText('Sayfa 1 / 2')).toBeInTheDocument());
    });

    it('reads every page of a scan the service returns in several pages', async () => {
        const backend = reviewBackend();
        backend.findings = Array.from({ length: 450 }, (_, index) => finding(1000 + index));
        renderApp(backend, { path: '/inventory' });

        expect(await screen.findByText('Bulgular: 450')).toBeInTheDocument();
        expect(findingCalls(backend)).toHaveLength(3);
    });

    it('downloads the CBOM with the bearer token and saves it as a file', async () => {
        const backend = reviewBackend();
        const downloads = captureDownloads();
        const user = userEvent.setup();
        renderApp(backend, { path: '/inventory' });

        await user.click(await screen.findByRole('button', { name: 'CBOM indir' }));

        await waitFor(() => expect(downloads.names).toEqual(['quancrypt-cbom-33333333.cdx.json']));
        expect(await downloads.blobs[0]?.text()).toBe('{"bomFormat":"CycloneDX","specVersion":"1.6"}');
        const call = backend.find('GET', '/artifact')[0];
        expect(call?.headers.get('Authorization')).toMatch(/^Bearer /);
        expect(call?.url.href).not.toContain('Bearer');
    });

    it('says so when the scan has no CBOM', async () => {
        const backend = reviewBackend();
        backend.artifact = null;
        const downloads = captureDownloads();
        const user = userEvent.setup();
        renderApp(backend, { path: '/inventory' });

        await user.click(await screen.findByRole('button', { name: 'CBOM indir' }));

        expect(await screen.findByText('Bu tarama için kaydedilmiş bir CBOM yok.')).toBeInTheDocument();
        expect(downloads.names).toHaveLength(0);
    });

    it('explains that nothing was scanned yet', async () => {
        const backend = reviewBackend();
        backend.overview = null;
        renderApp(backend, { path: '/inventory' });

        expect(await screen.findByText(/Henüz tamamlanmış bir tarama yok/)).toBeInTheDocument();
        expect(backend.find('GET', '/findings')).toHaveLength(0);
    });
});
