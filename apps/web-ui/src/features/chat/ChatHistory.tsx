import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { errorMessageKey } from '@/shared/api';
import type { SessionSummary } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { ErrorBanner } from '@/shared/ui';
import { DeleteHistoryDialog } from './components/DeleteHistoryDialog';
import { useDeleteChat, useSessions } from './hooks';
import { useChatRuns } from './runs';
import { groupSessions } from './sessionGroups';

/** The project's chats inside the sidebar (D-356b). Sessions that only hold a scan are not chats and are not listed. */
export function ChatHistory({ onNavigate }: { onNavigate?: () => void }) {
    const { project } = useProject();
    if (!project) return null;
    return <History key={project.id} projectId={project.id} onNavigate={onNavigate} />;
}

function History({ projectId, onNavigate }: { projectId: string; onNavigate?: () => void }) {
    const { t, language } = useI18n();
    const navigate = useNavigate();
    const onChatScreen = useLocation().pathname === '/chat';
    const sessions = useSessions(projectId);
    const { selected, select, runningKeys } = useChatRuns();
    const removal = useDeleteChat(projectId);
    const [search, setSearch] = useState('');
    // The chat the delete dialog was opened for: the shown chat may change while the dialog is open.
    const [deleteId, setDeleteId] = useState<string | null>(null);

    const activeId = onChatScreen ? selected(projectId) : null;
    const needle = search.trim().toLocaleLowerCase(language);
    const asked = (sessions.data ?? []).filter(
        (session): session is SessionSummary & { preview: string } => session.preview !== null,
    );
    const found = asked.filter((session) => session.preview.toLocaleLowerCase(language).includes(needle));
    const { today, earlier } = groupSessions(found, new Date());

    const open = (id: string) => {
        select(projectId, id);
        onNavigate?.();
        void navigate('/chat');
    };
    const closeDialog = () => {
        setDeleteId(null);
        removal.reset();
    };

    const group = (heading: string, items: SessionSummary[]) =>
        items.length === 0 ? null : (
            <section aria-label={heading} className="flex flex-col">
                <h3 className="m-0 px-2 pt-3 pb-1 text-xs font-semibold text-muted-foreground">{heading}</h3>
                <ul className="m-0 list-none p-0">
                    {items.map((session) => (
                        <li
                            key={session.id}
                            className={cn(
                                'group flex items-center rounded-lg hover:bg-accent',
                                session.id === activeId && 'bg-accent',
                            )}
                        >
                            <button
                                type="button"
                                aria-current={session.id === activeId}
                                onClick={() => open(session.id)}
                                className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 border-0 bg-transparent px-2 py-2 text-left font-[inherit] text-sm text-foreground"
                            >
                                <span className="min-w-0 flex-1 truncate">{session.preview}</span>
                                {runningKeys.has(session.id) ? (
                                    <>
                                        <span
                                            aria-hidden="true"
                                            className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-primary"
                                        />
                                        <span className="sr-only">{t('chat.sessions.running')}</span>
                                    </>
                                ) : null}
                            </button>
                            <button
                                type="button"
                                aria-label={t('chat.history.delete.named', {
                                    title: session.preview ?? '',
                                })}
                                title={t('chat.history.delete')}
                                disabled={runningKeys.has(session.id)}
                                onClick={() => setDeleteId(session.id)}
                                className="mr-1 shrink-0 cursor-pointer rounded-md border-0 bg-transparent p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100 disabled:cursor-default disabled:opacity-0 max-md:opacity-100"
                            >
                                <Trash2 aria-hidden="true" className="h-4 w-4" />
                            </button>
                        </li>
                    ))}
                </ul>
            </section>
        );

    return (
        <section aria-label={t('chat.sessions.title')} className="flex min-h-0 flex-1 flex-col gap-1">
            <Input
                type="search"
                aria-label={t('chat.sessions.search')}
                placeholder={t('chat.sessions.search')}
                autoComplete="off"
                spellCheck={false}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
            />
            <div className="min-h-0 flex-1 overflow-y-auto">
                {sessions.isError ? (
                    <p className="m-0 px-2 py-2 text-sm text-destructive">{t('chat.sessions.error')}</p>
                ) : found.length === 0 ? (
                    <p className="m-0 px-2 py-2 text-sm text-muted-foreground">{t('chat.sessions.none')}</p>
                ) : null}
                {group(t('chat.sessions.today'), today)}
                {group(t('chat.sessions.earlier'), earlier)}
            </div>
            {removal.error ? <ErrorBanner>{t(errorMessageKey(removal.error))}</ErrorBanner> : null}
            {deleteId !== null
                ? createPortal(
                      <DeleteHistoryDialog
                          busy={removal.isPending}
                          onConfirm={() => removal.mutate(deleteId, { onSuccess: () => setDeleteId(null) })}
                          onClose={closeDialog}
                      />,
                      document.body,
                  )
                : null}
        </section>
    );
}
