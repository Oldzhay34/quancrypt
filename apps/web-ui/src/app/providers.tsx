import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { ApiProvider } from '@/shared/api';
import { AuthProvider, NoTokenScreen, SessionInvalidScreen, useAuth } from '@/shared/auth';
import { I18nProvider } from '@/shared/i18n';
import { ProjectProvider } from '@/shared/project';
import { ActiveSessionProvider } from '@/shared/session';

function newQueryClient(): QueryClient {
    // A failed request is shown, not retried in the background: a 401 must reach the "session invalid" screen at once.
    return new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
}

/** With a token the data providers and the app run; without one (or after a 401) only the explaining screen is shown. */
function Authenticated({ children }: { children: ReactNode }) {
    const { status } = useAuth();
    if (status === 'missing') return <NoTokenScreen />;
    if (status === 'rejected') return <SessionInvalidScreen />;
    return (
        <ProjectProvider>
            <ActiveSessionProvider>{children}</ActiveSessionProvider>
        </ProjectProvider>
    );
}

export function AppProviders({ children, fetchImpl }: { children: ReactNode; fetchImpl?: typeof fetch }) {
    const [queryClient] = useState(newQueryClient);
    return (
        <I18nProvider>
            <AuthProvider>
                <QueryClientProvider client={queryClient}>
                    <ApiProvider fetchImpl={fetchImpl}>
                        <Authenticated>{children}</Authenticated>
                    </ApiProvider>
                </QueryClientProvider>
            </AuthProvider>
        </I18nProvider>
    );
}
