import type { MessageKey } from '@/shared/i18n';
import type { ClarificationQuestion, Evidence } from '@/shared/api/types';
import type { AgentEvent } from './events';

/**
 * The state of the turn being streamed and of the clarification form, as a pure reducer (testable without React).
 * A turn is one question and its answer, or one initial scan. It ends in exactly one terminal state and never leaves it.
 */
export type TurnStatus = 'streaming' | 'done' | 'refused' | 'stopped' | 'failed';

export interface Turn {
    kind: 'message' | 'scan';
    /** The user's text (null for a scan). */
    question: string | null;
    text: string;
    evidence: Evidence[];
    status: TurnStatus;
    /** The fixed refusal text of a `refusal` event. */
    refusal: string | null;
    /** What to tell the user about a stop or a failure. */
    failureKey: MessageKey | null;
    /** The stream was opened: the service has stored the user's message. */
    accepted: boolean;
    /** The stored history was reloaded after the turn ended. */
    synced: boolean;
}

export interface PendingClarification {
    questions: ClarificationQuestion[];
    /** The question that needs the answers: it is sent again once they are saved (D-291d). */
    question: string;
}

export interface ChatState {
    turn: Turn | null;
    clarification: PendingClarification | null;
}

export type ChatAction =
    | { type: 'start'; kind: 'message' | 'scan'; question: string | null }
    | { type: 'accepted' }
    | { type: 'event'; event: AgentEvent }
    | { type: 'failed'; key: MessageKey }
    | { type: 'synced' }
    | { type: 'clearClarification' }
    | { type: 'reset' };

export const initialChatState: ChatState = { turn: null, clarification: null };

const ERROR_KEYS = {
    stopped: 'chat.error.stopped',
    budget_exceeded: 'chat.error.budget_exceeded',
    llm_unavailable: 'chat.error.llm_unavailable',
    internal_error: 'chat.error.internal_error',
} as const satisfies Record<string, MessageKey>;

function dedupe(list: Evidence[], next: Evidence): Evidence[] {
    const same = list.some((item) => item.kind === next.kind && item.reference === next.reference);
    return same ? list : [...list, next];
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
    switch (action.type) {
        case 'start':
            return {
                clarification: null,
                turn: {
                    kind: action.kind,
                    question: action.question,
                    text: '',
                    evidence: [],
                    status: 'streaming',
                    refusal: null,
                    failureKey: null,
                    accepted: false,
                    synced: false,
                },
            };
        case 'accepted':
            return state.turn ? { ...state, turn: { ...state.turn, accepted: true } } : state;
        case 'event': {
            const turn = state.turn;
            if (!turn || turn.status !== 'streaming') return state;
            const event = action.event;
            switch (event.type) {
                case 'token':
                    return { ...state, turn: { ...turn, text: turn.text + event.text } };
                case 'evidence':
                    return { ...state, turn: { ...turn, evidence: dedupe(turn.evidence, event.evidence) } };
                case 'clarification_required':
                    // A scan never asks; only a question can be sent again after the answers are saved.
                    return turn.question === null
                        ? state
                        : {
                              ...state,
                              clarification: { questions: event.questions, question: turn.question },
                          };
                case 'refusal':
                    return { ...state, turn: { ...turn, status: 'refused', refusal: event.message } };
                case 'done':
                    return { ...state, turn: { ...turn, status: 'done' } };
                case 'error':
                    return {
                        ...state,
                        turn: {
                            ...turn,
                            status: event.code === 'stopped' ? 'stopped' : 'failed',
                            failureKey: ERROR_KEYS[event.code],
                        },
                    };
            }
            return state;
        }
        case 'failed':
            if (!state.turn || state.turn.status !== 'streaming') return state;
            return { ...state, turn: { ...state.turn, status: 'failed', failureKey: action.key } };
        case 'synced': {
            const turn = state.turn;
            if (!turn) return state;
            // The stored history now holds a finished answer: the live copy goes. A stop or a failure keeps its partial text.
            if (turn.status === 'done' || turn.status === 'refused') return { ...state, turn: null };
            return { ...state, turn: { ...turn, synced: true } };
        }
        case 'clearClarification':
            return { ...state, clarification: null };
        case 'reset':
            return initialChatState;
    }
}
