import { useMutation } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useApi } from '../api/ApiProvider';
import { stopSession } from './api';

interface ActiveSessionValue {
    /** The chat session that is running, or null. The chat screen (P5.3) sets it; the header Stop button reads it. */
    sessionId: string | null;
    setSessionId: (id: string | null) => void;
    stop: () => void;
    stopping: boolean;
}

const ActiveSessionContext = createContext<ActiveSessionValue | null>(null);

export function ActiveSessionProvider({ children }: { children: ReactNode }) {
    const api = useApi();
    const [sessionId, setSessionIdState] = useState<string | null>(null);
    const setSessionId = useCallback((id: string | null) => setSessionIdState(id), []);

    const stopMutation = useMutation({
        mutationFn: (id: string) => stopSession(api, id),
    });

    const value = useMemo<ActiveSessionValue>(
        () => ({
            sessionId,
            setSessionId,
            stop: () => {
                if (sessionId) stopMutation.mutate(sessionId);
            },
            stopping: stopMutation.isPending,
        }),
        [sessionId, setSessionId, stopMutation],
    );
    return <ActiveSessionContext.Provider value={value}>{children}</ActiveSessionContext.Provider>;
}

export function useActiveSession(): ActiveSessionValue {
    const value = useContext(ActiveSessionContext);
    if (!value) throw new Error('useActiveSession must be used inside ActiveSessionProvider');
    return value;
}
