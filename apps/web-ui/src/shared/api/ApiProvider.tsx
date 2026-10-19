import { createContext, useContext, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthProvider';
import { useI18n } from '../i18n/I18nProvider';
import { createApiClient } from './client';
import type { ApiClient } from './client';

const ApiContext = createContext<ApiClient | null>(null);

/**
 * A new client when the token or the language changes; queries and mutations read the current one on every render.
 * `fetchImpl` is for tests.
 */
export function ApiProvider({ children, fetchImpl }: { children: ReactNode; fetchImpl?: typeof fetch }) {
    const { token, rejectSession } = useAuth();
    const { language } = useI18n();

    const value = useMemo(
        () =>
            createApiClient({
                getToken: () => token,
                getLanguage: () => language,
                onUnauthorized: rejectSession,
                fetchImpl,
            }),
        [fetchImpl, token, language, rejectSession],
    );
    return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
    const value = useContext(ApiContext);
    if (!value) throw new Error('useApi must be used inside ApiProvider');
    return value;
}
