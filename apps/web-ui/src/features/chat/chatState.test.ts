import { describe, expect, it } from 'vitest';
import type { ClarificationQuestion } from '@/shared/api/types';
import { chatReducer, initialChatState } from './chatState';
import type { ChatAction, ChatState } from './chatState';

const run = (actions: ChatAction[], from: ChatState = initialChatState) => actions.reduce(chatReducer, from);

const start = (question: string | null = 'Soru'): ChatAction => ({
    type: 'start',
    kind: question === null ? 'scan' : 'message',
    question,
});

const question: ClarificationQuestion = {
    question_code: 'TLS_TERMINATION',
    text: { tr: 'TLS?', en: 'TLS?' },
    options: [{ option_code: 'YES', text: { tr: 'Evet', en: 'Yes' } }],
    answer_kind: 'OPTION',
    answer: null,
};

describe('chat reducer', () => {
    it('collects the tokens of a turn in order and ends it on done', () => {
        const state = run([
            start(),
            { type: 'accepted' },
            { type: 'event', event: { type: 'token', text: 'Mer' } },
            { type: 'event', event: { type: 'token', text: 'haba' } },
            { type: 'event', event: { type: 'done', messageId: 'm', llmDisabled: false } },
        ]);
        expect(state.turn).toMatchObject({
            text: 'Merhaba',
            status: 'done',
            accepted: true,
            question: 'Soru',
        });
    });

    it('keeps one chip per kind and reference', () => {
        const chip = { kind: 'code_location' as const, reference: 'A.java:3', source_version: null };
        const state = run([
            start(),
            { type: 'event', event: { type: 'evidence', evidence: chip } },
            { type: 'event', event: { type: 'evidence', evidence: chip } },
            {
                type: 'event',
                event: { type: 'evidence', evidence: { ...chip, kind: 'tool_call' as const } },
            },
        ]);
        expect(state.turn?.evidence).toHaveLength(2);
    });

    it('keeps the question with the clarification request, so it can be sent again', () => {
        const state = run([
            start('Hangi bulguları önce düzeltmeliyim?'),
            { type: 'event', event: { type: 'clarification_required', questions: [question] } },
            { type: 'event', event: { type: 'done', messageId: 'm', llmDisabled: false } },
        ]);
        expect(state.clarification).toEqual({
            questions: [question],
            question: 'Hangi bulguları önce düzeltmeliyim?',
        });
        expect(run([{ type: 'clearClarification' }], state).clarification).toBeNull();
    });

    it('never asks for answers after a scan', () => {
        const state = run([
            start(null),
            { type: 'event', event: { type: 'clarification_required', questions: [question] } },
        ]);
        expect(state.clarification).toBeNull();
    });

    it('ends in a refusal with the fixed text', () => {
        const state = run([start(), { type: 'event', event: { type: 'refusal', message: 'Anlamadım' } }]);
        expect(state.turn).toMatchObject({ status: 'refused', refusal: 'Anlamadım' });
    });

    it('maps a stop to "stopped" and the other errors to "failed", keeping the partial text', () => {
        const partial: ChatAction = { type: 'event', event: { type: 'token', text: 'yarım' } };
        const stopped = run([start(), partial, { type: 'event', event: { type: 'error', code: 'stopped' } }]);
        expect(stopped.turn).toMatchObject({
            status: 'stopped',
            text: 'yarım',
            failureKey: 'chat.error.stopped',
        });
        const failed = run([
            start(),
            partial,
            { type: 'event', event: { type: 'error', code: 'budget_exceeded' } },
        ]);
        expect(failed.turn).toMatchObject({
            status: 'failed',
            text: 'yarım',
            failureKey: 'chat.error.budget_exceeded',
        });
    });

    it('never leaves a terminal state', () => {
        const done = run([
            start(),
            { type: 'event', event: { type: 'done', messageId: 'm', llmDisabled: false } },
        ]);
        const after = run(
            [
                { type: 'event', event: { type: 'token', text: 'geç' } },
                { type: 'event', event: { type: 'error', code: 'internal_error' } },
                { type: 'failed', key: 'chat.error.protocol' },
            ],
            done,
        );
        expect(after).toBe(done);
    });

    it('drops the live copy of a finished answer once the history was reloaded, but keeps a stop', () => {
        const done = run([
            start(),
            { type: 'event', event: { type: 'done', messageId: 'm', llmDisabled: false } },
            { type: 'synced' },
        ]);
        expect(done.turn).toBeNull();
        const refused = run([
            start(),
            { type: 'event', event: { type: 'refusal', message: 'x' } },
            { type: 'synced' },
        ]);
        expect(refused.turn).toBeNull();
        const stopped = run([
            start(),
            { type: 'event', event: { type: 'token', text: 'yarım' } },
            { type: 'event', event: { type: 'error', code: 'stopped' } },
            { type: 'synced' },
        ]);
        expect(stopped.turn).toMatchObject({ status: 'stopped', text: 'yarım', synced: true });
    });

    it('starting a new turn clears an open clarification, reset clears everything', () => {
        const asked = run([
            start(),
            { type: 'event', event: { type: 'clarification_required', questions: [question] } },
        ]);
        expect(run([start('Başka')], asked).clarification).toBeNull();
        expect(run([{ type: 'reset' }], asked)).toEqual(initialChatState);
    });
});
