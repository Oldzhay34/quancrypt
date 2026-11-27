import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { FakeBackend, TOKEN, activeConsent, sse } from '@/test/fakeBackend';
import { renderApp } from '@/test/renderApp';

describe('Stop button', () => {
    it('appears while an answer runs and stops exactly that session with the bearer token', async () => {
        const backend = new FakeBackend();
        backend.consents = [activeConsent('MODEL_TRAINING')];
        const handle = backend.queueStream({});
        const user = userEvent.setup();
        renderApp(backend, { path: '/chat' });

        expect(screen.queryByRole('button', { name: 'Durdur' })).toBeNull();
        await user.type(await screen.findByRole('textbox', { name: 'Mesajınız' }), 'soru{Enter}');
        const stop = await screen.findByRole('button', { name: 'Durdur' });
        await waitFor(() => expect(stop).toBeEnabled());
        await user.click(stop);

        await waitFor(() => expect(backend.find('POST', '/stop')).toHaveLength(1));
        const call = backend.find('POST', '/stop')[0];
        const created = backend.find('POST', '/messages')[0]?.url.pathname.split('/')[4];
        expect(call?.url.pathname).toBe(`/api/v1/sessions/${created}/stop`);
        expect(call?.url.origin).toBe('http://127.0.0.1:8083');
        expect(call?.headers.get('Authorization')).toBe(`Bearer ${TOKEN}`);
        handle.push(sse('error', { code: 'stopped' }));
        handle.close();
    });
});
