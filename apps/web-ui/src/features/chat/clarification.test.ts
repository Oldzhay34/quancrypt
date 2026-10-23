import { describe, expect, it } from 'vitest';
import type { ClarificationQuestion } from '@/shared/api/types';
import { buildAnswers, initialDrafts } from './clarification';

const yesNo = [
    { option_code: 'YES', text: { tr: 'Evet', en: 'Yes' } },
    { option_code: 'NO', text: { tr: 'Hayır', en: 'No' } },
];

function question(
    code: string,
    kind: ClarificationQuestion['answer_kind'],
    answer: ClarificationQuestion['answer'] = null,
): ClarificationQuestion {
    return {
        question_code: code as ClarificationQuestion['question_code'],
        text: { tr: code, en: code },
        options: kind === 'TEXT' ? [] : yesNo,
        answer_kind: kind,
        answer,
    };
}

const questions = [
    question('JDK_UPGRADE_POSSIBLE', 'OPTION'),
    question('COMPLIANCE_REQUIREMENT', 'OPTION_WITH_TEXT'),
    question('DEVICE_HARDWARE_OPENSSL', 'TEXT'),
];

describe('clarification answers', () => {
    it('starts from the stored answers', () => {
        const drafts = initialDrafts([
            question('JDK_UPGRADE_POSSIBLE', 'OPTION', {
                question_code: 'JDK_UPGRADE_POSSIBLE',
                option_code: 'YES',
                free_text: null,
            }),
            question('DEVICE_HARDWARE_OPENSSL', 'TEXT'),
        ]);
        expect(drafts).toEqual({
            JDK_UPGRADE_POSSIBLE: { option: 'YES', text: '' },
            DEVICE_HARDWARE_OPENSSL: { option: null, text: '' },
        });
    });

    it('asks for an option on OPTION questions and sends no free text, even if some was typed', () => {
        const { answers, problems } = buildAnswers([questions[0] as ClarificationQuestion], {
            JDK_UPGRADE_POSSIBLE: { option: 'YES', text: 'sneaky' },
        });
        expect(problems).toEqual({});
        expect(answers).toEqual([
            { question_code: 'JDK_UPGRADE_POSSIBLE', option_code: 'YES', free_text: null },
        ]);
        const missing = buildAnswers([questions[0] as ClarificationQuestion], {});
        expect(missing.problems).toEqual({ JDK_UPGRADE_POSSIBLE: 'required' });
        expect(missing.answers).toEqual([]);
    });

    it('refuses an option the question does not offer', () => {
        const { problems } = buildAnswers([questions[0] as ClarificationQuestion], {
            JDK_UPGRADE_POSSIBLE: { option: 'MAYBE', text: '' },
        });
        expect(problems).toEqual({ JDK_UPGRADE_POSSIBLE: 'required' });
    });

    it('sends optional text with an option, trimmed, and null when there is none', () => {
        const q = questions[1] as ClarificationQuestion;
        expect(
            buildAnswers([q], { COMPLIANCE_REQUIREMENT: { option: 'YES', text: '  FIPS 140-3  ' } }).answers,
        ).toEqual([{ question_code: 'COMPLIANCE_REQUIREMENT', option_code: 'YES', free_text: 'FIPS 140-3' }]);
        expect(buildAnswers([q], { COMPLIANCE_REQUIREMENT: { option: 'NO', text: '   ' } }).answers).toEqual([
            { question_code: 'COMPLIANCE_REQUIREMENT', option_code: 'NO', free_text: null },
        ]);
    });

    it('needs text on a TEXT question and sends no option', () => {
        const q = questions[2] as ClarificationQuestion;
        expect(buildAnswers([q], { DEVICE_HARDWARE_OPENSSL: { option: 'YES', text: ' ' } }).problems).toEqual(
            {
                DEVICE_HARDWARE_OPENSSL: 'required',
            },
        );
        expect(
            buildAnswers([q], { DEVICE_HARDWARE_OPENSSL: { option: 'YES', text: 'OpenSSL 3.0' } }).answers,
        ).toEqual([
            { question_code: 'DEVICE_HARDWARE_OPENSSL', option_code: null, free_text: 'OpenSSL 3.0' },
        ]);
    });

    it('allows at most 500 characters of text', () => {
        const q = questions[2] as ClarificationQuestion;
        const ok = buildAnswers([q], { DEVICE_HARDWARE_OPENSSL: { option: null, text: 'a'.repeat(500) } });
        expect(ok.problems).toEqual({});
        const tooLong = buildAnswers([q], {
            DEVICE_HARDWARE_OPENSSL: { option: null, text: 'a'.repeat(501) },
        });
        expect(tooLong.problems).toEqual({ DEVICE_HARDWARE_OPENSSL: 'tooLong' });
        expect(tooLong.answers).toEqual([]);
    });

    it('reports every problem at once and builds nothing for a question with a problem', () => {
        const { answers, problems } = buildAnswers(questions, {
            JDK_UPGRADE_POSSIBLE: { option: 'NO', text: '' },
        });
        expect(answers).toEqual([
            { question_code: 'JDK_UPGRADE_POSSIBLE', option_code: 'NO', free_text: null },
        ]);
        expect(problems).toEqual({ COMPLIANCE_REQUIREMENT: 'required', DEVICE_HARDWARE_OPENSSL: 'required' });
    });
});
