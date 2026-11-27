import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect } from 'react';
import { ApiError, getScanSummary, getTopology, listScans, useApi } from '@/shared/api';
import type { ClarificationAnswer, Topology, ScanSummary } from '@/shared/api/types';
import { answerClarifications, deleteSession, listMessages, listSessions } from './api';
import { initialChatState } from './chatState';
import { draftKey, MAX_PARALLEL, scanKey, useChatRuns } from './runs';

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

/** The project's chat sessions for the list; refreshed after every turn and deletion. */
export function useSessions(projectId: string) {
    const api = useApi();
    return useQuery({
        queryKey: ['chat-sessions', projectId],
        queryFn: ({ signal }) => listSessions(api, projectId, signal),
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

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;

/**
 * Everything the chat screen does with the service, as a view of the app-wide runs store (D-351). The session is created
 * on the first message (not on opening the screen) and remembered per project (D-291c). One turn runs per chat
 * and at most {@link MAX_PARALLEL} in all; leaving the screen keeps them running.
 */
export function useChatController(projectId: string) {
    const api = useApi();
    const runs = useChatRuns();
    const sessionId = runs.selected(projectId);
    const key = sessionId ?? draftKey(projectId);
    const state = runs.entries.get(key)?.state ?? initialChatState;
    const busy = runs.runningKeys.has(key);
    const blocked = !busy && runs.runningKeys.size >= MAX_PARALLEL;
    const { discard, view, canStart, start, dispatch } = runs;

    useEffect(() => {
        view(key);
        return () => view(null);
    }, [key, view]);

    const forget = useCallback(() => {
        if (sessionId) discard(projectId, sessionId);
    }, [discard, projectId, sessionId]);
    const messages = useMessages(sessionId, forget);

    const send = useCallback(
        (text: string) => start(projectId, 'message', text, sessionId),
        [projectId, sessionId, start],
    );
    const stopRun = runs.stop;
    const stop = useCallback(() => stopRun(key), [stopRun, key]);

    const saveAnswers = useMutation({
        mutationFn: (request: { sessionId: string; answers: ClarificationAnswer[] }) =>
            answerClarifications(api, request.sessionId, request.answers),
    });
    const pending = state.clarification;
    const { mutateAsync: saveAsync } = saveAnswers;
    /** Saves the answers, then sends the question again to the chat that asked, wherever the user is by then (D-291d). */
    const submitClarifications = useCallback(
        async (answers: ClarificationAnswer[]) => {
            if (!pending || !sessionId) return;
            await saveAsync({ sessionId, answers });
            // Two other answers may have started meanwhile: the form stays, so that the question is not lost.
            if (!canStart(projectId, sessionId)) return;
            dispatch(sessionId, { type: 'clearClarification' });
            await start(projectId, 'message', pending.question, sessionId);
        },
        [canStart, dispatch, pending, projectId, saveAsync, sessionId, start],
    );

    return {
        sessionId,
        state,
        busy,
        blocked,
        epoch: runs.epoch,
        messages,
        send,
        stop,
        canStop: runs.stoppable.has(key),
        stopping: runs.stopping.has(key),
        submitClarifications,
        savingAnswers: saveAnswers.isPending && saveAnswers.variables?.sessionId === sessionId,
        answersError: saveAnswers.variables?.sessionId === sessionId ? saveAnswers.error : null,
        resetAnswersError: saveAnswers.reset,
    };
}

/** The project's scan as a view of the runs store (D-356c): its steps and answer stay until the next scan or a reload. */
export function useScanController(projectId: string) {
    const { entries, runningKeys, stoppable, stopping, start, stop, view } = useChatRuns();
    const key = scanKey(projectId);
    const state = entries.get(key)?.state ?? initialChatState;
    const busy = runningKeys.has(key);

    useEffect(() => {
        view(key);
        return () => view(null);
    }, [key, view]);

    return {
        state,
        busy,
        blocked: !busy && runningKeys.size >= MAX_PARALLEL,
        start: useCallback((root: string) => void start(projectId, 'scan', root, null), [projectId, start]),
        stop: useCallback(() => stop(key), [stop, key]),
        canStop: stoppable.has(key),
        stopping: stopping.has(key),
    };
}

/** Deletes a chat for good (D-225) and drops everything the app keeps about it. */
export function useDeleteChat(projectId: string) {
    const api = useApi();
    const client = useQueryClient();
    const { discard } = useChatRuns();
    return useMutation({
        mutationFn: async (id: string) => {
            try {
                await deleteSession(api, id);
            } catch (error) {
                if (!isNotFound(error)) throw error;
            }
        },
        onSuccess: (_, id) => {
            client.removeQueries({ queryKey: ['chat-messages', id] });
            void client.invalidateQueries({ queryKey: ['chat-sessions', projectId] });
            discard(projectId, id);
        },
    });
}
