import { render } from '@testing-library/react';
import { RouterProvider } from 'react-router';
import { AppProviders } from '@/app/providers';
import { createTestRouter } from '@/app/router';
import { TOKEN } from './fakeBackend';
import type { FakeBackend } from './fakeBackend';

/** Renders the whole app against a fake backend. `token: null` opens it without a session token. */
export function renderApp(backend: FakeBackend, options: { path?: string; token?: string | null } = {}) {
    const token = options.token === undefined ? TOKEN : options.token;
    window.history.replaceState(null, '', token ? `/#token=${token}` : '/');
    return render(
        <AppProviders fetchImpl={backend.fetch as typeof fetch}>
            <RouterProvider router={createTestRouter(options.path ?? '/')} />
        </AppProviders>,
    );
}
