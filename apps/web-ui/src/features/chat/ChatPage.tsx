import { ApiError, errorMessageKey } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { ErrorBanner } from '@/shared/ui';
import { cn } from '@/lib/utils';
import { useChatController, useLatestScan } from './hooks';
import { MAX_PARALLEL } from './runs';
import { ClarificationForm } from './components/ClarificationForm';
import { Composer } from './components/Composer';
import { MessageList } from './components/MessageList';
import styles from './components/Chat.module.css';
import { useStickToBottom } from './useStickToBottom';

const STATUS_KEYS = {
    streaming: 'chat.status.streaming',
    done: 'chat.status.done',
    refused: 'chat.status.refused',
    stopped: 'chat.status.stopped',
    failed: null,
} as const satisfies Record<string, MessageKey | null>;

/** The chat screen (UC2, UC3's questions, UC5). One component per project: switching the project starts a clean screen. */
export function ChatPage() {
    const { project } = useProject();
    if (!project) return null;
    return <ChatScreen key={project.id} projectId={project.id} />;
}

function ChatScreen({ projectId }: { projectId: string }) {
    const { t } = useI18n();
    const chat = useChatController(projectId);
    const latestScan = useLatestScan(projectId);
    const turn = chat.state.turn;
    const messages = chat.messages.data ?? [];
    const loading = chat.sessionId !== null && chat.messages.isPending;
    const empty = !loading && messages.length === 0 && turn === null;
    const { ref: scrollRef, onScroll } = useStickToBottom(
        messages.length,
        turn?.text,
        chat.state.steps.length,
        chat.state.clarification,
    );

    const statusKey = turn === null ? null : STATUS_KEYS[turn.status];
    const messagesError = chat.messages.error;
    const showMessagesError =
        chat.messages.isError && !(messagesError instanceof ApiError && messagesError.status === 404);

    return (
        <section className={cn(styles.screen, empty && styles.screenEmpty)}>
            <h1 className={styles.srOnly}>{t('nav.chat')}</h1>
            <p role="status" className={styles.srOnly}>
                {statusKey ? t(statusKey) : ''}
            </p>
            <div ref={scrollRef} onScroll={onScroll} className={styles.scroller}>
                <div className={styles.thread}>
                    {showMessagesError ? (
                        <ErrorBanner>{t(errorMessageKey(messagesError))}</ErrorBanner>
                    ) : null}
                    <MessageList
                        messages={messages}
                        turn={turn}
                        busy={chat.busy}
                        loading={loading}
                        steps={chat.state.steps}
                        needsScan={latestScan.data === null}
                    />
                    {turn?.failureKey ? (
                        turn.status === 'stopped' ? (
                            <p role="status" className={styles.notice}>
                                {t(turn.failureKey)}
                            </p>
                        ) : (
                            <ErrorBanner>{t(turn.failureKey)}</ErrorBanner>
                        )
                    ) : null}
                    {chat.state.clarification ? (
                        <ClarificationForm
                            key={`form-${chat.epoch}`}
                            questions={chat.state.clarification.questions}
                            busy={chat.busy}
                            blocked={chat.blocked}
                            saving={chat.savingAnswers}
                            failure={chat.answersError ? errorMessageKey(chat.answersError) : null}
                            onSubmit={(answers) =>
                                void chat.submitClarifications(answers).catch(() => undefined)
                            }
                        />
                    ) : null}
                </div>
            </div>
            <div className={styles.dock}>
                {chat.blocked ? (
                    <p role="status" className="m-0 text-sm text-muted-foreground">
                        {t('chat.parallel.limit', { count: String(MAX_PARALLEL) })}
                    </p>
                ) : null}
                <Composer
                    key={`composer-${chat.epoch}`}
                    busy={chat.busy}
                    blocked={chat.blocked}
                    canStop={chat.canStop}
                    stopping={chat.stopping}
                    onStop={chat.stop}
                    onSend={(text) => void chat.send(text)}
                />
            </div>
        </section>
    );
}
