import { useEffect, useId, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { ClarificationAnswer, ClarificationQuestion } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { Button, ErrorBanner } from '@/shared/ui';
import { buildAnswers, initialDrafts } from '../clarification';
import type { Draft, Problem } from '../clarification';
import { MAX_FREE_TEXT_CHARS } from '../limits';
import styles from './Clarification.module.css';

/** The service's option texts are the codes themselves; the labels the user reads are these, by code (unknown codes show the service's text). */
const OPTION_KEYS: Record<string, MessageKey> = {
    APPLICATION: 'chat.option.APPLICATION',
    INGRESS: 'chat.option.INGRESS',
    SERVICE_MESH: 'chat.option.SERVICE_MESH',
    LOAD_BALANCER: 'chat.option.LOAD_BALANCER',
    UNKNOWN: 'chat.option.UNKNOWN',
    YES: 'chat.option.YES',
    NO: 'chat.option.NO',
};

interface ClarificationFormProps {
    questions: ClarificationQuestion[];
    /** A turn is still streaming: the answers are saved when it has ended (the session is busy until then). */
    busy: boolean;
    saving: boolean;
    /** The message to show when saving failed. */
    failure: MessageKey | null;
    onSubmit: (answers: ClarificationAnswer[]) => void;
}

/** The clarification questions with structured inputs; what is asked and offered comes from the service's definitions. */
export function ClarificationForm({ questions, busy, saving, failure, onSubmit }: ClarificationFormProps) {
    const { t, language } = useI18n();
    const [drafts, setDrafts] = useState<Record<string, Draft>>(() => initialDrafts(questions));
    const [problems, setProblems] = useState<Record<string, Problem>>({});
    const form = useRef<HTMLFormElement>(null);
    const heading = useRef<HTMLHeadingElement>(null);
    const id = useId();

    useEffect(() => {
        heading.current?.focus();
    }, []);

    // After a failed check the focus goes to the first control that needs an answer.
    useEffect(() => {
        if (Object.keys(problems).length > 0) {
            form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
        }
    }, [problems]);

    const change = (code: string, patch: Partial<Draft>) =>
        setDrafts((current) => ({
            ...current,
            [code]: { option: null, text: '', ...current[code], ...patch },
        }));

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (busy || saving) return;
        const result = buildAnswers(questions, drafts);
        setProblems(result.problems);
        if (Object.keys(result.problems).length === 0) onSubmit(result.answers);
    };

    return (
        <form ref={form} className={styles.form} onSubmit={submit} noValidate>
            <h2 ref={heading} tabIndex={-1} className={styles.title}>
                {t('chat.clarify.title')}
            </h2>
            <p className={styles.intro}>{t('chat.clarify.intro')}</p>
            {questions.map((question) => {
                const code = question.question_code;
                const draft = drafts[code];
                const problem = problems[code];
                const errorId = `${id}-${code}-error`;
                const textId = `${id}-${code}-text`;
                const hasText = question.answer_kind !== 'OPTION';
                const optionProblem = problem === 'required' && question.answer_kind !== 'TEXT';
                const textProblem =
                    problem === 'tooLong' || (problem === 'required' && question.answer_kind === 'TEXT');
                return (
                    <fieldset
                        key={code}
                        className={styles.question}
                        aria-describedby={problem ? errorId : undefined}
                    >
                        <legend>{question.text[language]}</legend>
                        {question.options.map((option) => (
                            <label key={option.option_code} className={styles.option}>
                                <input
                                    type="radio"
                                    name={`${id}-${code}`}
                                    value={option.option_code}
                                    checked={draft?.option === option.option_code}
                                    aria-invalid={optionProblem}
                                    onChange={() => change(code, { option: option.option_code })}
                                />
                                {OPTION_KEYS[option.option_code]
                                    ? t(OPTION_KEYS[option.option_code] as MessageKey)
                                    : option.text[language]}
                            </label>
                        ))}
                        {hasText ? (
                            <div className={styles.text}>
                                <label htmlFor={textId}>
                                    {question.answer_kind === 'TEXT'
                                        ? t('chat.clarify.text')
                                        : t('chat.clarify.textOptional')}
                                </label>
                                <textarea
                                    id={textId}
                                    rows={2}
                                    maxLength={MAX_FREE_TEXT_CHARS}
                                    value={draft?.text ?? ''}
                                    aria-invalid={textProblem}
                                    onChange={(event) => change(code, { text: event.target.value })}
                                />
                            </div>
                        ) : null}
                        {problem ? (
                            <p id={errorId} role="alert" className={styles.error}>
                                {problem === 'required'
                                    ? t('chat.clarify.required')
                                    : t('chat.clarify.tooLong')}
                            </p>
                        ) : null}
                    </fieldset>
                );
            })}
            {failure ? <ErrorBanner>{t(failure)}</ErrorBanner> : null}
            <div className={styles.actions}>
                <Button type="submit" variant="primary" disabled={busy || saving}>
                    {saving ? t('chat.clarify.saving') : t('chat.clarify.submit')}
                </Button>
                {busy ? <p className={styles.waiting}>{t('chat.clarify.waiting')}</p> : null}
            </div>
        </form>
    );
}
