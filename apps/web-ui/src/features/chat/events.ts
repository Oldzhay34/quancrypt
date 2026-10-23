import type { SseMessage } from '@/shared/api';
import type { ClarificationQuestion, Evidence } from '@/shared/api/types';

/** The six event types of the agent-service streams (contract `x-sse-events`), checked at runtime: the body comes from the network. */
export type AgentErrorCode = 'stopped' | 'budget_exceeded' | 'llm_unavailable' | 'internal_error';

export type AgentEvent =
    | { type: 'token'; text: string }
    | { type: 'evidence'; evidence: Evidence }
    | { type: 'clarification_required'; questions: ClarificationQuestion[] }
    | { type: 'refusal'; message: string }
    | { type: 'done'; messageId: string; llmDisabled: boolean }
    | { type: 'error'; code: AgentErrorCode };

/** A stream event that does not match the contract. */
export class ProtocolError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'ProtocolError';
    }
}

type Json = Record<string, unknown>;

const ERROR_CODES: readonly string[] = ['stopped', 'budget_exceeded', 'llm_unavailable', 'internal_error'];
const EVIDENCE_KINDS: readonly string[] = ['code_location', 'tool_call', 'knowledge_base'];
const ANSWER_KINDS: readonly string[] = ['OPTION', 'OPTION_WITH_TEXT', 'TEXT'];

const isRecord = (value: unknown): value is Json =>
    typeof value === 'object' && value !== null && !Array.isArray(value);

function text(value: unknown, field: string): string {
    if (typeof value !== 'string') throw new ProtocolError(`${field}: text expected`);
    return value;
}

function parse(data: string): Json {
    let value: unknown;
    try {
        value = JSON.parse(data);
    } catch {
        throw new ProtocolError('event data is not JSON');
    }
    if (!isRecord(value)) throw new ProtocolError('event data is not an object');
    return value;
}

function decodeEvidence(value: unknown): Evidence {
    if (!isRecord(value)) throw new ProtocolError('evidence: object expected');
    const kind = text(value.kind, 'evidence.kind');
    if (!EVIDENCE_KINDS.includes(kind)) throw new ProtocolError('evidence.kind: unknown kind');
    const version = value.source_version;
    const title = value.title;
    return {
        kind: kind as Evidence['kind'],
        reference: text(value.reference, 'evidence.reference').slice(0, 1024),
        source_version: typeof version === 'string' ? version.slice(0, 64) : null,
        ...(typeof title === 'string' && title !== '' ? { title: title.slice(0, 200) } : {}),
    };
}

function decodeLocalized(value: unknown, field: string): { tr: string; en: string } {
    if (!isRecord(value)) throw new ProtocolError(`${field}: object expected`);
    return { tr: text(value.tr, `${field}.tr`), en: text(value.en, `${field}.en`) };
}

function decodeQuestion(value: unknown): ClarificationQuestion {
    if (!isRecord(value)) throw new ProtocolError('question: object expected');
    const kind = text(value.answer_kind, 'question.answer_kind');
    if (!ANSWER_KINDS.includes(kind)) throw new ProtocolError('question.answer_kind: unknown kind');
    if (!Array.isArray(value.options)) throw new ProtocolError('question.options: list expected');
    const options = value.options.map((option: unknown) => {
        if (!isRecord(option)) throw new ProtocolError('option: object expected');
        return {
            option_code: text(option.option_code, 'option.option_code'),
            text: decodeLocalized(option.text, 'option.text'),
        };
    });
    const code = text(
        value.question_code,
        'question.question_code',
    ) as ClarificationQuestion['question_code'];
    let answer: ClarificationQuestion['answer'] = null;
    if (isRecord(value.answer)) {
        const given = value.answer;
        answer = {
            question_code: code,
            option_code: typeof given.option_code === 'string' ? given.option_code : null,
            free_text: typeof given.free_text === 'string' ? given.free_text : null,
        };
    }
    return {
        question_code: code,
        text: decodeLocalized(value.text, 'question.text'),
        options,
        answer_kind: kind as ClarificationQuestion['answer_kind'],
        answer,
    };
}

/** The typed event of an SSE message, `null` for an event type the UI does not know, `ProtocolError` for a malformed one. */
export function decodeAgentEvent(message: SseMessage): AgentEvent | null {
    switch (message.event) {
        case 'token':
            return { type: 'token', text: text(parse(message.data).text, 'token.text') };
        case 'evidence':
            return { type: 'evidence', evidence: decodeEvidence(parse(message.data).evidence) };
        case 'clarification_required': {
            const questions = parse(message.data).questions;
            if (!Array.isArray(questions) || questions.length === 0)
                throw new ProtocolError('questions: a list is expected');
            return { type: 'clarification_required', questions: questions.map(decodeQuestion) };
        }
        case 'refusal':
            return { type: 'refusal', message: text(parse(message.data).message, 'refusal.message') };
        case 'done': {
            const data = parse(message.data);
            return {
                type: 'done',
                messageId: text(data.message_id, 'done.message_id'),
                llmDisabled: data.llm_disabled === true,
            };
        }
        case 'error': {
            const code = text(parse(message.data).code, 'error.code');
            if (!ERROR_CODES.includes(code)) throw new ProtocolError('error.code: unknown code');
            return { type: 'error', code: code as AgentErrorCode };
        }
        default:
            return null;
    }
}
