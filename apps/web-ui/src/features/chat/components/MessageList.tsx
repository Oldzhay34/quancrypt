import { Fragment } from 'react';
import type { ChatMessage, StepEvent } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { Spinner } from '@/shared/ui';
import type { Turn } from '../chatState';
import { EmptyHero } from './EmptyHero';
import { MessageBubble } from './MessageBubble';
import { ReasoningSteps } from './ReasoningSteps';
import styles from './Chat.module.css';

interface MessageListProps {
    messages: ChatMessage[];
    /** The turn being streamed, or the last stopped or failed one. */
    turn: Turn | null;
    busy: boolean;
    loading: boolean;
    /** The steps of the last answer of this screen (D-350f). */
    steps: StepEvent[];
    /** The project has no completed scan yet: the empty screen points to the analysis. */
    needsScan: boolean;
}

/**
 * The conversation: a live region (`role="log"`, polite) that is `aria-busy` while an answer streams, so a screen reader waits for
 * the finished text instead of reading every 64-character piece.
 */
export function MessageList({ messages, turn, busy, loading, steps, needsScan }: MessageListProps) {
    const { t } = useI18n();
    // Once the stored history holds the user's message, the live copy of it goes: after the turn is synced, or already
    // while it runs when the history was read again (the user came back to this chat).
    const last = messages.at(-1);
    const stored = turn?.accepted === true && last?.role === 'user' && last.content === turn.question;
    const question = turn !== null && !(turn.accepted && turn.synced) && !stored ? turn.question : null;
    const showAnswer =
        turn !== null && (turn.text !== '' || turn.refusal !== null || turn.evidence.length > 0);
    const waiting = turn?.status === 'streaming' && turn.text === '' && turn.refusal === null;
    return (
        <div
            role="log"
            aria-live="polite"
            aria-relevant="additions text"
            aria-busy={busy}
            aria-label={t('chat.log.label')}
            className={styles.log}
        >
            {loading ? <Spinner label={t('common.loading')} /> : null}
            {!loading && messages.length === 0 && turn === null ? <EmptyHero needsScan={needsScan} /> : null}
            {messages.map((message, index) => (
                <Fragment key={message.id}>
                    {turn === null && index === messages.length - 1 && message.role === 'assistant' ? (
                        <ReasoningSteps steps={steps} running={false} />
                    ) : null}
                    <MessageBubble
                        author={message.role}
                        text={message.content}
                        evidence={message.evidence ?? []}
                    />
                </Fragment>
            ))}
            {question !== null ? <MessageBubble author="user" text={question} /> : null}
            {turn !== null || messages.at(-1)?.role !== 'assistant' ? (
                <ReasoningSteps steps={steps} running={turn?.status === 'streaming'} />
            ) : null}
            {showAnswer ? (
                <MessageBubble
                    author={turn.kind === 'scan' ? 'scan' : 'assistant'}
                    text={turn.refusal ?? turn.text}
                    evidence={turn.evidence}
                    refusal={turn.refusal !== null}
                />
            ) : null}
            {waiting ? (
                <Spinner label={t(turn.kind === 'scan' ? 'chat.scan.running' : 'chat.status.streaming')} />
            ) : null}
        </div>
    );
}
