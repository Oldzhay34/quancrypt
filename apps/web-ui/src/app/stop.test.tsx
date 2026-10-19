import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { useActiveSession } from '@/shared/session';
import { FakeBackend, TOKEN } from '@/test/fakeBackend';
import { AppProviders } from './providers';
import { Header } from './layout/Header';

/** Stands in for the chat screen (P5.3), which announces the running session. */
function RunningSession({ id }: { id: string }) {
    const { setSessionId } = useActiveSession();
    useEffect(() => setSessionId(id), [id, setSessionId]);
    return null;
}

describe('Stop button', () => {
    it('is enabled while a session runs and stops exactly that session with the bearer token', async () => {
        const backend = new FakeBackend();
        window.history.replaceState(null, '', `/#token=${TOKEN}`);
        const user = userEvent.setup();
        render(
            <AppProviders fetchImpl={backend.fetch as typeof fetch}>
                <RunningSession id="s-1" />
                <Header />
            </AppProviders>,
        );

        const stop = await screen.findByRole('button', { name: 'Durdur' });
        await waitFor(() => expect(stop).toBeEnabled());
        await user.click(stop);

        await waitFor(() => expect(backend.find('POST', '/api/v1/sessions/s-1/stop')).toHaveLength(1));
        const call = backend.find('POST', '/stop')[0];
        expect(call?.url.origin).toBe('http://127.0.0.1:8083');
        expect(call?.headers.get('Authorization')).toBe(`Bearer ${TOKEN}`);
    });
});
