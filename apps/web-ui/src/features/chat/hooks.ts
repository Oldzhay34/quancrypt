import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
    ApiError,
    errorMessageKey,
    getScanSummary,
    getTopology,
    listScans,
    readSseStream,
    SseError,
    useApi,
} from '@/shared/api';
import type { ClarificationAnswer, Topology, ScanSummary } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { useActiveSession } from '@/shared/session';
import {
    answerClarifications,
    createSession,
    deleteSession,
    listMessages,
    streamInitialScan,
    streamMessage,
} from './api';
import { chatReducer, initialChatState } from './chatState';
import { decodeAgentEvent, ProtocolError } from './events';
import { forgetSessionId, loadSessionId, saveSessionId } from './sessionStore';

function failureKey(error: unknown): MessageKey {
    if (error instanceof ProtocolError || error instanceof SseError) return 'chat.error.protocol';
    if (error instanceof ApiError && error.code === 'protocol') return 'chat.error.protocol';
    return errorMessageKey(error);
}

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;

/**
 * The stored history of a session (`['chat-messages', id]`); not asked for before there is a session. `onGone` is called when the
 * service says it does not know the session (deleted elsewhere), so the screen can start over with a new one.
 */
export function useMessages(sessionId: string | null, onGone: () => void) {
    const api = useApi();
    return useQuery({
        queryKey: ['chat-messages', sessionId],
        enabled: sessionId !== null,
        queryFn: async ({ signal }) => {
            try {
                return await listMessages(api, sessionId as string, signal);
            } catch (error) {
                if (isNotFound(error)) onGone();
                throw error;
            }
        },
    });
}

export interface ScanOverview {
    summary: ScanSummary;
    /** Null when the scan has no recorded topology. */
    topology: Topology | null;
}

/** The newest completed scan of the project with its summary and topology, or null when it was never scanned. */
export function useLatestScan(projectId: string) {
    const api = useApi();
    return useQuery({
        queryKey: ['scan-summary', projectId],
        queryFn: async ({ signal }): Promise<ScanOverview | null> => {
            const scans = await listScans(api, projectId, signal);
            const latest = scans.find((scan) => scan.status === 'COMPLETED');
            if (!latest) return null;
            const [summary, topology] = await Promise.all([
                getScanSummary(api, latest.id, signal),
                getTopology(api, latest.id, signal),
            ]);
            return { summary, topology };
        },
    });
}

/**
 * Everything the chat screen does with the service. The session is created on the first message or scan (not on opening the
 * screen, so looking around leaves no empty session behind) and remembered per project (D-291c). One turn runs at a time: a
 * message or a scan is streamed, its events go through the reducer, and the stored history is reloaded when it ends. Leaving the
 * screen cancels the request; the service then stops the run. The header's Stop button is enabled only while a turn streams.
 */
export function useChatController(projectId: string) {
    const api = useApi();
    const { language } = useI18n();
    const client = useQueryClient();
    const { setSessionId: announce } = useActiveSession();
    const [sessionId, setSessionId] = useState<string | null>(() => loadSessionId(projectId));
    const [state, dispatch] = useReducer(chatReducer, initialChatState);
    const abort = useRef<AbortController | null>(null);
    const creating = useRef<Promise<string> | null>(null);
    const running = useRef(false);

    const forget = useCallback(() => {
        forgetSessionId(projectId);
        setSessionId(null);
    }, [projectId]);

    const messages = useMessages(sessionId, forget);

    useEffect(
        () => () => {
            abort.current?.abort();
            announce(null);
        },
        [announce],
    );

    const ensureSession = useCallback((): Promise<string> => {
        if (sessionId) return Promise.resolve(sessionId);
        creating.current ??= createSession(api, projectId, language)
            .then((session) => {
                saveSessionId(projectId, session.id);
                setSessionId(session.id);
                return session.id;
            })
            .finally(() => {
                creating.current = null;
            });
        return creating.current;
    }, [api, language, projectId, sessionId]);

    const run = useCallback(
        async (kind: 'message' | 'scan', payload: string) => {
            if (running.current) return;
            running.current = true;
            const controller = new AbortController();
            abort.current = controller;
            dispatch({ type: 'start', kind, question: kind === 'message' ? payload : null });
            let id: string | null = null;
            let ended = false;
            try {
                id = await ensureSession();
                announce(id);
                const body =
                    kind === 'message'
                        ? await streamMessage(api, id, payload, controller.signal)
                        : await streamInitialScan(api, id, payload, controller.signal);
                dispatch({ type: 'accepted' });
                for await (const message of readSseStream(body, controller.signal)) {
                    const event = decodeAgentEvent(message);
                    if (event === null) continue;
                    if (event.type === 'done' || event.type === 'refusal' || event.type === 'error')
                        ended = true;
                    dispatch({ type: 'event', event });
                }
                if (!ended && !controller.signal.aborted)
                    dispatch({ type: 'failed', key: 'chat.error.protocol' });
            } catch (error) {
                if (!controller.signal.aborted) {
                    dispatch({ type: 'failed', key: failureKey(error) });
                    if (id !== null && isNotFound(error)) forget();
                }
            } finally {
                announce(null);
                running.current = false;
                abort.current = null;
                if (id !== null && !controller.signal.aborted) {
                    await Promise.all([
                        client.invalidateQueries({ queryKey: ['chat-messages', id] }),
                        kind === 'scan'
                            ? client.invalidateQueries({ queryKey: ['scan-summary', projectId] })
                            : Promise.resolve(),
                    ]);
                    dispatch({ type: 'synced' });
                }
            }
        },
        [announce, api, client, ensureSession, forget, projectId],
    );

    const send = useCallback((text: string) => run('message', text), [run]);
    const startScan = useCallback((root: string) => run('scan', root), [run]);

    const saveAnswers = useMutation({
        mutationFn: (answers: ClarificationAnswer[]) =>
            answerClarifications(api, sessionId as string, answers),
    });
    const pending = state.clarification;
    const { mutateAsync: saveAsync } = saveAnswers;
    /** Saves the answers, then sends the question that needed them again: the plan flow continues (D-291d). */
    const submitClarifications = useCallback(
        async (answers: ClarificationAnswer[]) => {
            if (!pending || !sessionId) return;
            await saveAsync(answers);
            dispatch({ type: 'clearClarification' });
            await run('message', pending.question);
        },
        [pending, run, saveAsync, sessionId],
    );

    const removeHistory = useMutation({
        mutationFn: async () => {
            if (!sessionId) return;
            abort.current?.abort();
            try {
                await deleteSession(api, sessionId);
            } catch (error) {
                if (!isNotFound(error)) throw error;
            }
        },
        onSuccess: () => {
            client.removeQueries({ queryKey: ['chat-messages', sessionId] });
            forget();
            dispatch({ type: 'reset' });
        },
    });

    return {
        sessionId,
        state,
        busy: state.turn?.status === 'streaming',
        messages,
        send,
        startScan,
        submitClarifications,
        savingAnswers: saveAnswers.isPending,
        answersError: saveAnswers.error,
        resetAnswersError: saveAnswers.reset,
        removeHistory: removeHistory.mutate,
        removingHistory: removeHistory.isPending,
        removeError: removeHistory.error,
        resetRemoveError: removeHistory.reset,
    };
}
