import type { ClarificationAnswer, ClarificationQuestion } from '@/shared/api/types';
import { MAX_FREE_TEXT_CHARS } from './limits';

/**
 * What the form sends, by the question's `answer_kind` (the agent-service's definition, D-291b): `OPTION` an option and no text
 * (core refuses text there), `OPTION_WITH_TEXT` an option and optional text, `TEXT` text and no option. Pure, so the rules are
 * tested without React.
 */
export interface Draft {
    option: string | null;
    text: string;
}

export type Problem = 'required' | 'tooLong';

export function initialDrafts(questions: ClarificationQuestion[]): Record<string, Draft> {
    return Object.fromEntries(
        questions.map((question) => [
            question.question_code,
            { option: question.answer?.option_code ?? null, text: question.answer?.free_text ?? '' },
        ]),
    );
}

export function buildAnswers(
    questions: ClarificationQuestion[],
    drafts: Record<string, Draft>,
): { answers: ClarificationAnswer[]; problems: Record<string, Problem> } {
    const answers: ClarificationAnswer[] = [];
    const problems: Record<string, Problem> = {};
    for (const question of questions) {
        const code = question.question_code;
        const draft = drafts[code] ?? { option: null, text: '' };
        const text = draft.text.trim();
        if (text.length > MAX_FREE_TEXT_CHARS) {
            problems[code] = 'tooLong';
            continue;
        }
        if (question.answer_kind === 'TEXT') {
            if (text === '') problems[code] = 'required';
            else answers.push({ question_code: code, option_code: null, free_text: text });
            continue;
        }
        const known = draft.option !== null && question.options.some((o) => o.option_code === draft.option);
        if (!known) {
            problems[code] = 'required';
            continue;
        }
        const freeText = question.answer_kind === 'OPTION_WITH_TEXT' && text !== '' ? text : null;
        answers.push({ question_code: code, option_code: draft.option, free_text: freeText });
    }
    return { answers, problems };
}
