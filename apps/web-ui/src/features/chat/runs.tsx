import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError, errorMessageKey, readSseStream, SseError, useApi } from '@/shared/api';
import type { MessageKey } from '@/shared/i18n';
import { useI18n } from '@/shared/i18n';
import { stopSession } from '@/shared/session';
import { createSession, streamInitialScan, streamMessage } from './api';
import { chatReducer, initialChatState } from './chatState';
import type { ChatAction, ChatState } from './chatState';
import { decodeAgentEvent, ProtocolError } from './events';
import { forgetSessionId, loadSessionId, saveSessionId } from './sessionStore';

/**
 * The answers being streamed (D-351). They belong to the app, not to the chat screen: switching the chat or the screen
 * keeps them running, at most {@link MAX_PARALLEL} at a time, and an answer that ends where the user is not looking
 * becomes a notice card. Closing the tab or losing the session token still cancels them (the service then stops the run).
 */
export const MAX_PARALLEL = 2;

export type RunKind = 'message' | 'scan';

/** The key of a chat that has no session yet. */
export const draftKey = (projectId: string) => `new:${projectId}`;
/** The key of a project's scan (D-356c): it has its own session and is never a chat. */
export const scanKey = (projectId: string) => `scan:${projectId}`;
export const isScanKey = (key: string) => key.startsWith('scan:');

export interface RunEntry {
    projectId: string;
    state: ChatState;
}

export type NoticeKind = 'done' | 'failed' | 'question';

export interface Notice {
    id: number;
    projectId: string;
    /** The run it is about: a chat's session id, or the project's scan key. */
    key: string;
    kind: NoticeKind;
    /** What was asked; null for a scan. */
    title: string | null;
}

interface RunsValue {
    entries: ReadonlyMap<string, RunEntry>;
    runningKeys: ReadonlySet<string>;
    notices: readonly Notice[];
    /** Counts the times another chat was chosen; a draft turning into its session does not count. */
    epoch: number;
    /** The chosen chat of a project (null: a new one). */
    selected: (projectId: string) => string | null;
    select: (projectId: string, sessionId: string | null) => void;
    /** Starts a message or a scan on the chosen chat of the project; false when it cannot start now. */
    canStart: (projectId: string, sessionId: string | null) => boolean;
    start: (projectId: string, kind: RunKind, payload: string, sessionId: string | null) => Promise<boolean>;
    dispatch: (key: string, action: ChatAction) => void;
    /** Cancels the run of a chat and drops everything kept about it (it was deleted or is gone). */
    discard: (projectId: string, key: string) => void;
    /** The chat the screen is showing now (null when the screen is not open). */
    view: (key: string | null) => void;
    dismiss: (noticeId: number) => void;
    /** The runs the service already knows, and can therefore be asked to stop. */
    stoppable: ReadonlyMap<string, string>;
    stopping: ReadonlySet<string>;
    /** Asks the service to end the run of this key (D-356d). */
    stop: (key: string) => void;
}

const RunsContext = createContext<RunsValue | null>(null);

function failureKey(error: unknown): MessageKey {
    if (error instanceof ProtocolError || error instanceof SseError) return 'chat.error.protocol';
    if (error instanceof ApiError && error.code === 'protocol') return 'chat.error.protocol';
    return errorMessageKey(error);
}

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;

export function ChatRunsProvider({ children }: { children: ReactNode }) {
    const api = useApi();
    const { language } = useI18n();
    const client = useQueryClient();

    const [entries, setEntries] = useState<ReadonlyMap<string, RunEntry>>(new Map());
    const [runningKeys, setRunningKeys] = useState<ReadonlySet<string>>(new Set());
    const [notices, setNotices] = useState<readonly Notice[]>([]);
    const [selection, setSelection] = useState<ReadonlyMap<string, string | null>>(new Map());
    const [stoppable, setStoppable] = useState<ReadonlyMap<string, string>>(new Map());
    const [stopping, setStopping] = useState<ReadonlySet<string>>(new Set());
    const [epoch, setEpoch] = useState(0);

    // Synchronous mirrors: the limit and the "still wanted" checks cannot wait for a render.
    const controllers = useRef(new Map<string, AbortController>());
    const viewingRef = useRef<string | null>(null);
    const selectionRef = useRef<ReadonlyMap<string, string | null>>(new Map());
    const noticeId = useRef(0);
    const serverIds = useRef(new Map<string, string>());

    const syncRunning = useCallback(() => {
        for (const key of serverIds.current.keys()) {
            if (!controllers.current.has(key)) serverIds.current.delete(key);
        }
        setRunningKeys(new Set(controllers.current.keys()));
        setStoppable(new Map(serverIds.current));
    }, []);

    const stop = useCallback(
        (key: string) => {
            const sessionId = serverIds.current.get(key);
            if (!sessionId) return;
            setStopping((all) => new Set(all).add(key));
            // The stream itself reports the result; a failed stop leaves the run as it is.
            void stopSession(api, sessionId)
                .catch(() => undefined)
                .finally(() =>
                    setStopping((all) => {
                        const next = new Set(all);
                        next.delete(key);
                        return next;
                    }),
                );
        },
        [api],
    );

    const selected = useCallback(
        (projectId: string) =>
            selection.has(projectId) ? (selection.get(projectId) ?? null) : loadSessionId(projectId),
        [selection],
    );

    const show = useCallback((projectId: string, sessionId: string | null) => {
        if (sessionId === null) forgetSessionId(projectId);
        else saveSessionId(projectId, sessionId);
        const next = new Map(selectionRef.current).set(projectId, sessionId);
        selectionRef.current = next;
        setSelection(next);
        if (sessionId !== null) setNotices((all) => all.filter((n) => n.key !== sessionId));
    }, []);

    const select = useCallback(
        (projectId: string, sessionId: string | null) => {
            const current = selectionRef.current.has(projectId)
                ? (selectionRef.current.get(projectId) ?? null)
                : loadSessionId(projectId);
            if (current !== sessionId) setEpoch((n) => n + 1);
            show(projectId, sessionId);
        },
        [show],
    );

    const dispatch = useCallback((key: string, action: ChatAction) => {
        setEntries((all) => {
            const entry = all.get(key);
            if (!entry) return all;
            return new Map(all).set(key, { ...entry, state: chatReducer(entry.state, action) });
        });
    }, []);

    const view = useCallback((key: string | null) => {
        viewingRef.current = key;
        if (key !== null) setNotices((all) => all.filter((n) => n.key !== key));
    }, []);

    const dismiss = useCallback((id: number) => setNotices((all) => all.filter((n) => n.id !== id)), []);

    const discard = useCallback(
        (projectId: string, key: string) => {
            controllers.current.get(key)?.abort();
            controllers.current.delete(key);
            syncRunning();
            setEntries((all) => {
                const next = new Map(all);
                next.delete(key);
                return next;
            });
            setNotices((all) => all.filter((n) => n.key !== key));
            if ((selectionRef.current.get(projectId) ?? loadSessionId(projectId)) === key)
                select(projectId, null);
        },
        [select, syncRunning],
    );

    /** Whether `start` would accept a run for this chat right now. */
    const canStart = useCallback(
        (projectId: string, sessionId: string | null) =>
            !controllers.current.has(sessionId ?? draftKey(projectId)) &&
            controllers.current.size < MAX_PARALLEL,
        [],
    );

    const start = useCallback(
        async (projectId: string, kind: RunKind, payload: string, sessionId: string | null) => {
            // A scan always gets a session of its own and leaves the chosen chat alone (D-356c).
            const scan = kind === 'scan';
            let key = scan ? scanKey(projectId) : (sessionId ?? draftKey(projectId));
            if (controllers.current.has(key) || controllers.current.size >= MAX_PARALLEL) return false;
            const controller = new AbortController();
            controllers.current.set(key, controller);
            syncRunning();
            const question = kind === 'message' ? payload : null;
            setEntries((all) => {
                const state = all.get(key)?.state ?? initialChatState;
                return new Map(all).set(key, {
                    projectId,
                    state: chatReducer(state, { type: 'start', kind, question }),
                });
            });

            let id: string | null = scan ? null : sessionId;
            let ended = false;
            let outcome: NoticeKind = 'done';
            let asked = false;
            try {
                if (id === null) {
                    const session = await createSession(api, projectId, language);
                    id = session.id;
                    if (controller.signal.aborted) return true;
                    if (!scan) {
                        // The draft becomes the session; the screen follows only if the user still looks at the draft.
                        const old = key;
                        key = id;
                        controllers.current.delete(old);
                        controllers.current.set(key, controller);
                        setEntries((all) => {
                            const entry = all.get(old);
                            const next = new Map(all);
                            next.delete(old);
                            if (entry) next.set(key, entry);
                            return next;
                        });
                        saveSessionId(projectId, id);
                        if ((selectionRef.current.get(projectId) ?? null) === null) show(projectId, id);
                        if (viewingRef.current === old) view(key);
                    }
                }
                serverIds.current.set(key, id);
                syncRunning();
                const body =
                    kind === 'message'
                        ? await streamMessage(api, id, payload, controller.signal)
                        : await streamInitialScan(api, id, payload, controller.signal);
                dispatch(key, { type: 'accepted' });
                let listed = false;
                for await (const message of readSseStream(body, controller.signal)) {
                    const event = decodeAgentEvent(message);
                    if (event === null) continue;
                    // The service stores the question before its first event: from then on the chat is in the list.
                    if (!listed && !scan) {
                        listed = true;
                        void client.invalidateQueries({ queryKey: ['chat-sessions', projectId] });
                    }
                    if (event.type === 'done' || event.type === 'refusal' || event.type === 'error')
                        ended = true;
                    if (event.type === 'error') outcome = 'failed';
                    if (event.type === 'clarification_required') asked = true;
                    dispatch(key, { type: 'event', event });
                }
                if (!ended && !controller.signal.aborted) {
                    outcome = 'failed';
                    dispatch(key, { type: 'failed', key: 'chat.error.protocol' });
                }
            } catch (error) {
                outcome = 'failed';
                if (!controller.signal.aborted) {
                    dispatch(key, { type: 'failed', key: failureKey(error) });
                    if (!scan && id !== null && isNotFound(error)) {
                        forgetSessionId(projectId);
                        select(projectId, null);
                    }
                }
            } finally {
                if (controllers.current.get(key) === controller) controllers.current.delete(key);
                syncRunning();
                if (!controller.signal.aborted) {
                    if (id !== null && viewingRef.current !== key) {
                        const done = key;
                        const notice: Notice = {
                            id: ++noticeId.current,
                            projectId,
                            key: done,
                            kind: outcome === 'done' && asked ? 'question' : outcome,
                            title: question,
                        };
                        setNotices((all) => [...all.filter((n) => n.key !== done), notice].slice(-3));
                    }
                    if (scan) {
                        // The result stays on the analysis screen; only the summary is read again.
                        await client.invalidateQueries({ queryKey: ['scan-summary', projectId] });
                    } else if (id !== null) {
                        await Promise.all([
                            client.invalidateQueries({ queryKey: ['chat-sessions', projectId] }),
                            client.invalidateQueries({ queryKey: ['chat-messages', id] }),
                        ]);
                        dispatch(key, { type: 'synced' });
                    }
                }
            }
            return true;
        },
        [api, client, dispatch, language, select, show, syncRunning, view],
    );

    useEffect(() => {
        const all = controllers.current;
        return () => {
            all.forEach((controller) => controller.abort());
            all.clear();
        };
    }, []);

    const value = useMemo<RunsValue>(
        () => ({
            entries,
            runningKeys,
            notices,
            epoch,
            selected,
            select,
            canStart,
            start,
            dispatch,
            discard,
            view,
            dismiss,
            stoppable,
            stopping,
            stop,
        }),
        [
            entries,
            runningKeys,
            notices,
            epoch,
            selected,
            select,
            canStart,
            start,
            dispatch,
            discard,
            view,
            dismiss,
            stoppable,
            stopping,
            stop,
        ],
    );
    return <RunsContext.Provider value={value}>{children}</RunsContext.Provider>;
}

export function useChatRuns(): RunsValue {
    const value = useContext(RunsContext);
    if (!value) throw new Error('useChatRuns must be used inside ChatRunsProvider');
    return value;
}
