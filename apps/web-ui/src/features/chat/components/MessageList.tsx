import type { ChatMessage } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { Spinner } from '@/shared/ui';
import type { Turn } from '../chatState';
import { MessageBubble } from './MessageBubble';
import styles from './Chat.module.css';

interface MessageListProps {
    messages: ChatMessage[];
    /** The turn being streamed, or the last stopped or failed one. */
    turn: Turn | null;
    busy: boolean;
    loading: boolean;
}

/**
 * The conversation: a live region (`role="log"`, polite) that is `aria-busy` while an answer streams, so a screen reader waits for
 * the finished text instead of reading every 64-character piece.
 */
export function MessageList({ messages, turn, busy, loading }: MessageListProps) {
    const { t } = useI18n();
    // Once the stored history holds the user's message, the live copy of it goes.
    const question = turn !== null && !(turn.accepted && turn.synced) ? turn.question : null;
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
            {!loading && messages.length === 0 && turn === null ? (
                <p className={styles.empty}>{t('chat.empty')}</p>
            ) : null}
            {messages.map((message) => (
                <MessageBubble
                    key={message.id}
                    author={message.role}
                    text={message.content}
                    evidence={message.evidence ?? []}
                />
            ))}
            {question !== null ? <MessageBubble author="user" text={question} /> : null}
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
