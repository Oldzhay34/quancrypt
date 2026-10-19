import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { acquireToken, clearStoredToken } from './token';

export type AuthStatus = 'missing' | 'ready' | 'rejected';

interface AuthContextValue {
    status: AuthStatus;
    token: string | null;
    /** Called when the services answer 401: the token is dropped and the "session invalid" screen is shown. */
    rejectSession: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [token, setToken] = useState<string | null>(() => acquireToken());
    const [rejected, setRejected] = useState(false);

    const rejectSession = useCallback(() => {
        clearStoredToken();
        setToken(null);
        setRejected(true);
    }, []);

    const value = useMemo<AuthContextValue>(
        () => ({ status: token ? 'ready' : rejected ? 'rejected' : 'missing', token, rejectSession }),
        [token, rejected, rejectSession],
    );
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
    const value = useContext(AuthContext);
    if (!value) throw new Error('useAuth must be used inside AuthProvider');
    return value;
}
