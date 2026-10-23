import { describe, expect, it } from 'vitest';
import { decodeAgentEvent, ProtocolError } from './events';

const decode = (event: string, data: unknown) =>
    decodeAgentEvent({ event, data: typeof data === 'string' ? data : JSON.stringify(data) });

describe('decodeAgentEvent', () => {
    it('decodes a token', () => {
        expect(decode('token', { text: 'Merhaba' })).toEqual({ type: 'token', text: 'Merhaba' });
    });

    it('decodes evidence, keeps the title of a knowledge-base entry and cuts over-long values', () => {
        const event = decode('evidence', {
            evidence: {
                kind: 'knowledge_base',
                reference: 'https://example.org/jep-496',
                source_version: 'JEP 496',
                title: 'ML-KEM in the JDK',
            },
        });
        expect(event).toEqual({
            type: 'evidence',
            evidence: {
                kind: 'knowledge_base',
                reference: 'https://example.org/jep-496',
                source_version: 'JEP 496',
                title: 'ML-KEM in the JDK',
            },
        });
        const long = decode('evidence', {
            evidence: { kind: 'code_location', reference: 'x'.repeat(2000), source_version: null },
        });
        expect(long).toMatchObject({ type: 'evidence', evidence: { reference: 'x'.repeat(1024) } });
    });

    it('leaves the title out when the service sent none', () => {
        const event = decode('evidence', {
            evidence: { kind: 'tool_call', reference: 'abc', source_version: null },
        });
        expect(event).toEqual({
            type: 'evidence',
            evidence: { kind: 'tool_call', reference: 'abc', source_version: null },
        });
    });

    it('rejects evidence of an unknown kind or without a reference', () => {
        expect(() => decode('evidence', { evidence: { kind: 'other', reference: 'r' } })).toThrow(
            ProtocolError,
        );
        expect(() => decode('evidence', { evidence: { kind: 'tool_call' } })).toThrow(ProtocolError);
        expect(() => decode('evidence', {})).toThrow(ProtocolError);
    });

    it('decodes the questions of a clarification request with their answer kinds', () => {
        const event = decode('clarification_required', {
            questions: [
                {
                    question_code: 'COMPLIANCE_REQUIREMENT',
                    text: { tr: 'Uyum?', en: 'Compliance?' },
                    options: [{ option_code: 'YES', text: { tr: 'Evet', en: 'Yes' } }],
                    answer_kind: 'OPTION_WITH_TEXT',
                    answer: { option_code: 'YES', free_text: 'FIPS' },
                },
                {
                    question_code: 'DEVICE_HARDWARE_OPENSSL',
                    text: { tr: 'Cihaz?', en: 'Device?' },
                    options: [],
                    answer_kind: 'TEXT',
                    answer: null,
                },
            ],
        });
        expect(event).toMatchObject({
            type: 'clarification_required',
            questions: [
                {
                    question_code: 'COMPLIANCE_REQUIREMENT',
                    answer_kind: 'OPTION_WITH_TEXT',
                    answer: {
                        question_code: 'COMPLIANCE_REQUIREMENT',
                        option_code: 'YES',
                        free_text: 'FIPS',
                    },
                },
                { question_code: 'DEVICE_HARDWARE_OPENSSL', answer_kind: 'TEXT', answer: null },
            ],
        });
    });

    it('rejects a clarification request that is empty or has an unknown answer kind', () => {
        expect(() => decode('clarification_required', { questions: [] })).toThrow(ProtocolError);
        expect(() =>
            decode('clarification_required', {
                questions: [
                    {
                        question_code: 'X',
                        text: { tr: 'a', en: 'b' },
                        options: [],
                        answer_kind: 'CHECKBOX',
                        answer: null,
                    },
                ],
            }),
        ).toThrow(ProtocolError);
    });

    it('decodes refusal, done and every error code', () => {
        expect(decode('refusal', { message: 'Anlamadım' })).toEqual({
            type: 'refusal',
            message: 'Anlamadım',
        });
        expect(decode('done', { message_id: 'm-1', llm_disabled: true })).toEqual({
            type: 'done',
            messageId: 'm-1',
            llmDisabled: true,
        });
        expect(decode('done', { message_id: 'm-1' })).toMatchObject({ llmDisabled: false });
        for (const code of ['stopped', 'budget_exceeded', 'llm_unavailable', 'internal_error']) {
            expect(decode('error', { code })).toEqual({ type: 'error', code });
        }
        expect(() => decode('error', { code: 'boom' })).toThrow(ProtocolError);
    });

    it('ignores an event type it does not know and refuses data that is not a JSON object', () => {
        expect(decode('progress', { percent: 5 })).toBeNull();
        expect(() => decode('token', 'not json')).toThrow(ProtocolError);
        expect(() => decode('token', '[1,2]')).toThrow(ProtocolError);
        expect(() => decode('token', { text: 5 })).toThrow(ProtocolError);
    });
});
