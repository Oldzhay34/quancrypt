import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/renderApp';
import { reviewBackend } from '@/test/review';

const probes = (backend: ReturnType<typeof reviewBackend>) =>
    backend.calls.filter((call) => call.url.port === '8088');

describe('dashboard link', () => {
    it('shows the link to Superset when it answers, opening in a new tab without the opener', async () => {
        const backend = reviewBackend();
        backend.supersetUp = true;
        renderApp(backend, { path: '/chat' });

        const link = await screen.findByRole('link', { name: 'Dashboard' });
        expect(link).toHaveAttribute('href', 'http://127.0.0.1:8088');
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('hides the link when Superset does not answer', async () => {
        const backend = reviewBackend();
        backend.supersetUp = false;
        renderApp(backend, { path: '/chat' });

        await waitFor(() => expect(probes(backend).length).toBeGreaterThan(0));
        await screen.findByRole('heading', { name: 'Sohbet' });
        expect(screen.queryByRole('link', { name: 'Dashboard' })).toBeNull();
    });

    it('probes without sending the session token or any other credential', async () => {
        const backend = reviewBackend();
        backend.supersetUp = true;
        renderApp(backend, { path: '/chat' });
        await screen.findByRole('link', { name: 'Dashboard' });

        const probe = probes(backend)[0];
        expect(probe?.headers.get('Authorization')).toBeNull();
        expect(probe?.method).toBe('GET');
    });
});
