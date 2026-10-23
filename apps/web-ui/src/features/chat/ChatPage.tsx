import { useCallback, useState } from 'react';
import { ApiError, errorMessageKey } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { Button, ErrorBanner, Page } from '@/shared/ui';
import { useChatController, useLatestScan } from './hooks';
import { ClarificationForm } from './components/ClarificationForm';
import { Composer } from './components/Composer';
import { DeleteHistoryDialog } from './components/DeleteHistoryDialog';
import { InitialScanPanel } from './components/InitialScanPanel';
import { MessageList } from './components/MessageList';
import styles from './components/Chat.module.css';

const STATUS_KEYS = {
    streaming: 'chat.status.streaming',
    done: 'chat.status.done',
    refused: 'chat.status.refused',
    stopped: 'chat.status.stopped',
    failed: null,
} as const satisfies Record<string, MessageKey | null>;

/** The chat screen (UC1, UC2, UC3's questions, UC5). One component per project: switching the project starts a clean screen. */
export function ChatPage() {
    const { project } = useProject();
    if (!project) return null;
    return <ChatScreen key={project.id} projectId={project.id} />;
}

function ChatScreen({ projectId }: { projectId: string }) {
    const { t } = useI18n();
    const chat = useChatController(projectId);
    const latestScan = useLatestScan(projectId);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const { resetRemoveError, removeHistory } = chat;

    const closeDialog = useCallback(() => {
        setConfirmDelete(false);
        resetRemoveError();
    }, [resetRemoveError]);
    const confirmRemoval = useCallback(
        () => removeHistory(undefined, { onSuccess: () => setConfirmDelete(false) }),
        [removeHistory],
    );

    const turn = chat.state.turn;
    const statusKey = turn === null ? null : STATUS_KEYS[turn.status];
    const messagesError = chat.messages.error;
    const showMessagesError =
        chat.messages.isError && !(messagesError instanceof ApiError && messagesError.status === 404);

    return (
        <Page title={t('nav.chat')}>
            <InitialScanPanel
                overview={latestScan.data}
                loadError={latestScan.error}
                busy={chat.busy}
                scanning={chat.busy && turn?.kind === 'scan'}
                onStart={(root) => void chat.startScan(root)}
            />
            <p role="status" className={styles.srOnly}>
                {statusKey ? t(statusKey) : ''}
            </p>
            {showMessagesError ? <ErrorBanner>{t(errorMessageKey(messagesError))}</ErrorBanner> : null}
            <MessageList
                messages={chat.messages.data ?? []}
                turn={turn}
                busy={chat.busy}
                loading={chat.sessionId !== null && chat.messages.isPending}
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
                    questions={chat.state.clarification.questions}
                    busy={chat.busy}
                    saving={chat.savingAnswers}
                    failure={chat.answersError ? errorMessageKey(chat.answersError) : null}
                    onSubmit={(answers) => void chat.submitClarifications(answers).catch(() => undefined)}
                />
            ) : null}
            <Composer busy={chat.busy} onSend={(text) => void chat.send(text)} />
            <div className={styles.toolbar}>
                <Button
                    disabled={chat.sessionId === null || chat.busy}
                    onClick={() => setConfirmDelete(true)}
                >
                    {t('chat.history.delete')}
                </Button>
            </div>
            {confirmDelete ? (
                <DeleteHistoryDialog
                    busy={chat.removingHistory}
                    onConfirm={confirmRemoval}
                    onClose={closeDialog}
                />
            ) : null}
            {chat.removeError ? <ErrorBanner>{t(errorMessageKey(chat.removeError))}</ErrorBanner> : null}
        </Page>
    );
}
