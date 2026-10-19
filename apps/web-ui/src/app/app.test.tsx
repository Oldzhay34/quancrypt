import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { FakeBackend, NOTICE, PROJECT, TOKEN, activeConsent } from '@/test/fakeBackend';
import { renderApp } from '@/test/renderApp';

const WAREHOUSE = /Analitik \(WAREHOUSE_ANALYTICS\)/;
const TRAINING = /Model eğitimi \(MODEL_TRAINING\)/;

describe('opening the app', () => {
    it('shows an explaining screen without a token and calls no service', async () => {
        const backend = new FakeBackend();
        renderApp(backend, { token: null });

        expect(await screen.findByRole('heading', { name: 'Oturum anahtarı yok' })).toBeInTheDocument();
        expect(backend.calls).toHaveLength(0);
    });

    it('removes the token from the address bar and sends it as a bearer header', async () => {
        const backend = new FakeBackend();
        renderApp(backend);

        await screen.findByRole('heading', { name: 'Aydınlatma metni ve onaylar' });
        expect(window.location.hash).toBe('');
        expect(window.location.href).not.toContain(TOKEN);
        expect(backend.calls.every((call) => call.headers.get('Authorization') === `Bearer ${TOKEN}`)).toBe(
            true,
        );
    });

    it('shows the consent screen first, with the latest notice and both switches off', async () => {
        renderApp(new FakeBackend());

        expect(
            await screen.findByRole('heading', { name: 'Aydınlatma metni ve onaylar' }),
        ).toBeInTheDocument();
        expect(screen.getByText('Aydınlatma metni sürüm 2', { exact: false })).toBeInTheDocument();
        expect(screen.getByText(/Aydınlatma metni v2/)).toBeInTheDocument();
        expect(screen.getByRole('switch', { name: WAREHOUSE })).not.toBeChecked();
        expect(screen.getByRole('switch', { name: TRAINING })).not.toBeChecked();
        expect(screen.getByText('Bu metin hukuki görüş değildir.')).toBeInTheDocument();
    });

    it('shows the notice as text, never as HTML', async () => {
        const backend = new FakeBackend();
        backend.notice = { ...NOTICE, textTr: '<img src=x onerror=alert(1)> güvenli metin' };
        const { container } = renderApp(backend);

        await screen.findByText(/güvenli metin/);
        expect(container.querySelector('img')).toBeNull();
    });

    it('shows "session invalid" when a service answers 401', async () => {
        const backend = new FakeBackend();
        backend.unauthorized = true;
        renderApp(backend);

        expect(await screen.findByRole('heading', { name: 'Oturum geçersiz' })).toBeInTheDocument();
        expect(screen.getByText(/\.quancrypt\/session\.token/)).toBeInTheDocument();
        expect(window.sessionStorage.getItem('quancrypt.session')).toBeNull();
    });

    it('explains when no project is registered', async () => {
        const backend = new FakeBackend();
        backend.projects = [];
        renderApp(backend);

        expect(await screen.findByRole('heading', { name: 'Kayıtlı proje yok' })).toBeInTheDocument();
    });
});

describe('consent flow', () => {
    it('continues without any consent: nothing is saved, the app opens, and the screen is not shown again', async () => {
        const backend = new FakeBackend();
        const user = userEvent.setup();
        renderApp(backend);

        await user.click(await screen.findByRole('button', { name: 'Devam et' }));

        expect(await screen.findByRole('heading', { name: 'Sohbet' })).toBeInTheDocument();
        expect(backend.find('POST', '/consents')).toHaveLength(0);
        expect(window.localStorage.getItem(`consentSeen:${PROJECT.id}:2`)).toBe('1');
    });

    it('saves only the switches that were turned on', async () => {
        const backend = new FakeBackend();
        const user = userEvent.setup();
        renderApp(backend);

        await user.click(await screen.findByRole('switch', { name: WAREHOUSE }));
        await user.click(screen.getByRole('button', { name: 'Devam et' }));

        await screen.findByRole('heading', { name: 'Sohbet' });
        const posts = backend.find('POST', '/consents');
        expect(posts).toHaveLength(1);
        expect(posts[0]?.body).toEqual({ consentType: 'WAREHOUSE_ANALYTICS', privacyNoticeVersion: 2 });
        expect(posts[0]?.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
        expect(posts[0]?.headers.get('If-Match')).toBeNull();
        expect(backend.consents.map((consent) => consent.consentType)).toEqual(['WAREHOUSE_ANALYTICS']);
    });

    it('shows a clear error and stays on the screen when saving fails', async () => {
        const backend = new FakeBackend();
        const user = userEvent.setup();
        renderApp(backend);
        await user.click(await screen.findByRole('switch', { name: TRAINING }));
        backend.failNext = 409;

        await user.click(screen.getByRole('button', { name: 'Devam et' }));

        expect(await screen.findByRole('alert')).toHaveTextContent('başka bir yerden değiştirilmiş');
        expect(screen.getByRole('heading', { name: 'Aydınlatma metni ve onaylar' })).toBeInTheDocument();
    });

    it('does not ask again once consents of the current notice version exist', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('MODEL_TRAINING')];
        renderApp(backend);

        expect(await screen.findByRole('heading', { name: 'Sohbet' })).toBeInTheDocument();
    });

    it('shows the consents that are really active when it asks again, and does not change them by continuing', async () => {
        const backend = new FakeBackend();
        backend.consents = [{ ...activeConsent('MODEL_TRAINING'), privacyNoticeVersion: 1 }];
        const user = userEvent.setup();
        renderApp(backend);

        const training = await screen.findByRole('switch', { name: TRAINING });
        expect(training).toBeChecked();
        expect(screen.getByRole('switch', { name: WAREHOUSE })).not.toBeChecked();
        await user.click(screen.getByRole('button', { name: 'Devam et' }));

        await screen.findByRole('heading', { name: 'Sohbet' });
        expect(backend.find('POST', '/consents')).toHaveLength(0);
        expect(backend.find('DELETE', '/consents')).toHaveLength(0);
        expect(backend.consents[0]?.privacyNoticeVersion).toBe(1);
        expect(window.localStorage.getItem(`consentSeen:${PROJECT.id}:2`)).toBe('1');
    });

    it('withdraws an active consent that was turned off on the screen', async () => {
        const backend = new FakeBackend();
        backend.consents = [{ ...activeConsent('MODEL_TRAINING', 5), privacyNoticeVersion: 1 }];
        const user = userEvent.setup();
        renderApp(backend);

        await user.click(await screen.findByRole('switch', { name: TRAINING }));
        await user.click(screen.getByRole('button', { name: 'Devam et' }));

        await screen.findByRole('heading', { name: 'Sohbet' });
        const deletes = backend.find('DELETE', '/consents/MODEL_TRAINING');
        expect(deletes).toHaveLength(1);
        expect(deletes[0]?.headers.get('If-Match')).toBe('"5"');
    });

    it('asks again for a new notice version', async () => {
        const backend = new FakeBackend();
        backend.consents = [{ ...activeConsent('MODEL_TRAINING'), privacyNoticeVersion: 1 }];
        renderApp(backend);

        expect(
            await screen.findByRole('heading', { name: 'Aydınlatma metni ve onaylar' }),
        ).toBeInTheDocument();
    });
});

describe('settings', () => {
    it('shows the current consents and lets the user withdraw one after a warning (UC6)', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('WAREHOUSE_ANALYTICS', 3)];
        const user = userEvent.setup();
        renderApp(backend, { path: '/settings' });

        const warehouse = await screen.findByRole('switch', { name: WAREHOUSE });
        expect(warehouse).toBeChecked();
        expect(screen.getByRole('switch', { name: TRAINING })).not.toBeChecked();

        await user.click(warehouse);
        const dialog = await screen.findByRole('dialog', { name: 'Onayı geri çek' });
        expect(
            within(dialog).getByText(/warehouse’taki kayıtlarının silinmesi istenecek/),
        ).toBeInTheDocument();
        expect(backend.find('DELETE', '/consents')).toHaveLength(0);

        await user.click(within(dialog).getByRole('button', { name: 'Onayla' }));

        await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
        const deletes = backend.find('DELETE', '/consents/WAREHOUSE_ANALYTICS');
        expect(deletes).toHaveLength(1);
        expect(deletes[0]?.headers.get('If-Match')).toBe('"3"');
        await waitFor(() => expect(screen.getByRole('switch', { name: WAREHOUSE })).not.toBeChecked());
    });

    it('keeps the consent when the warning is cancelled', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('WAREHOUSE_ANALYTICS')];
        const user = userEvent.setup();
        renderApp(backend, { path: '/settings' });

        await user.click(await screen.findByRole('switch', { name: WAREHOUSE }));
        await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Vazgeç' }));

        expect(screen.queryByRole('dialog')).toBeNull();
        expect(backend.find('DELETE', '/consents')).toHaveLength(0);
        expect(screen.getByRole('switch', { name: WAREHOUSE })).toBeChecked();
    });

    it('grants a withdrawn consent again with If-Match (its version)', async () => {
        const backend = new FakeBackend();
        backend.consents = [{ ...activeConsent('MODEL_TRAINING', 4), revokedAt: '2026-10-19T13:00:00Z' }];
        const user = userEvent.setup();
        renderApp(backend, { path: '/settings' });

        await user.click(await screen.findByRole('switch', { name: TRAINING }));

        await waitFor(() => expect(screen.getByRole('switch', { name: TRAINING })).toBeChecked());
        const posts = backend.find('POST', '/consents');
        expect(posts[0]?.headers.get('If-Match')).toBe('"4"');
        expect(posts[0]?.body).toEqual({ consentType: 'MODEL_TRAINING', privacyNoticeVersion: 2 });
    });

    it('can show the notice again in the chosen language', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('MODEL_TRAINING')];
        const user = userEvent.setup();
        renderApp(backend, { path: '/settings' });

        await user.click(await screen.findByRole('button', { name: 'Aydınlatma metnini göster' }));
        expect(screen.getByText(/Aydınlatma metni v2/)).toBeInTheDocument();

        await user.selectOptions(screen.getByRole('combobox', { name: 'Dil' }), 'en');
        expect(await screen.findByText(/Privacy notice v2/)).toBeInTheDocument();
        expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    });
});

describe('layout', () => {
    it('shows the project name, the five menu entries and a disabled Stop button without an active session', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('MODEL_TRAINING')];
        renderApp(backend);

        await screen.findByRole('heading', { name: 'Sohbet' });
        expect(screen.getByTitle('Proje')).toHaveTextContent('qbank');
        const nav = screen.getByRole('navigation', { name: 'Ana menü' });
        expect(
            within(nav)
                .getAllByRole('link')
                .map((link) => link.textContent),
        ).toEqual(['Sohbet', 'Envanter', 'Topoloji', 'Plan', 'Ayarlar']);
        expect(screen.getByRole('button', { name: 'Durdur' })).toBeDisabled();
    });

    it('lets the user pick a project when there are several, and remembers the choice for the tab', async () => {
        const backend = new FakeBackend();
        backend.projects = [
            PROJECT,
            { ...PROJECT, id: '22222222-2222-4222-8222-222222222222', displayName: 'other' },
        ];
        backend.consents = [activeConsent('MODEL_TRAINING')];
        const user = userEvent.setup();
        renderApp(backend);

        const select = await screen.findByRole('combobox', { name: 'Proje' });
        await user.selectOptions(select, 'other');

        expect(window.sessionStorage.getItem('quancrypt.project')).toBe(
            '22222222-2222-4222-8222-222222222222',
        );
        await waitFor(() =>
            expect(
                backend.find('GET', '/22222222-2222-4222-8222-222222222222/consents').length,
            ).toBeGreaterThan(0),
        );
    });

    it('opens in the saved language and sets the page language at start', async () => {
        window.localStorage.setItem('quancrypt.lang', 'en');
        const backend = new FakeBackend();
        backend.consents = [activeConsent('MODEL_TRAINING')];
        renderApp(backend);

        expect(await screen.findByRole('heading', { name: 'Chat' })).toBeInTheDocument();
        expect(document.documentElement.lang).toBe('en');
    });

    it('switches the whole interface to English', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('MODEL_TRAINING')];
        const user = userEvent.setup();
        renderApp(backend);

        await user.selectOptions(await screen.findByRole('combobox', { name: 'Dil' }), 'en');

        expect(await screen.findByRole('heading', { name: 'Chat' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
        expect(document.documentElement.lang).toBe('en');
    });
});
