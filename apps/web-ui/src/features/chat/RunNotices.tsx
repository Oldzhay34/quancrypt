import { CheckCircle2, CircleAlert, MessageCircleQuestion, X } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Button } from '@/components/ui/button';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { isScanKey, useChatRuns } from './runs';
import type { Notice, NoticeKind } from './runs';

const TITLES: Record<NoticeKind, MessageKey> = {
    done: 'chat.notice.done',
    failed: 'chat.notice.failed',
    question: 'chat.notice.question',
};

const ICONS = {
    done: <CheckCircle2 aria-hidden="true" className="h-5 w-5 text-primary" />,
    failed: <CircleAlert aria-hidden="true" className="h-5 w-5 text-destructive" />,
    question: <MessageCircleQuestion aria-hidden="true" className="h-5 w-5 text-primary" />,
};

/** Cards at the bottom for answers that ended in a chat the user is not looking at (D-351). */
export function RunNotices() {
    const { t } = useI18n();
    const { notices, select, dismiss } = useChatRuns();
    const { selectProject } = useProject();
    const navigate = useNavigate();

    const open = (notice: Notice) => {
        selectProject(notice.projectId);
        const scan = isScanKey(notice.key);
        if (!scan) select(notice.projectId, notice.key);
        dismiss(notice.id);
        void navigate(scan ? '/analysis' : '/chat');
    };

    return (
        <div
            role="status"
            aria-label={t('chat.notice.label')}
            className="pointer-events-none fixed right-4 bottom-4 z-[5] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2 print:hidden"
        >
            {notices.map((notice) => (
                <div
                    key={notice.id}
                    className="pointer-events-auto flex gap-3 rounded-xl border border-border bg-card p-3 text-foreground shadow-lg"
                >
                    {ICONS[notice.kind]}
                    <div className="min-w-0 flex-1">
                        <p className="m-0 text-sm font-semibold">
                            {isScanKey(notice.key) && notice.kind === 'done'
                                ? t('chat.notice.analysisDone')
                                : t(TITLES[notice.kind])}
                        </p>
                        <p className="m-0 truncate text-xs text-muted-foreground">
                            {notice.title ?? t('chat.sessions.scanOnly')}
                        </p>
                        <Button variant="outline" size="sm" className="mt-2" onClick={() => open(notice)}>
                            {isScanKey(notice.key) ? t('chat.notice.openAnalysis') : t('chat.notice.open')}
                        </Button>
                    </div>
                    <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t('chat.notice.dismiss')}
                        onClick={() => dismiss(notice.id)}
                    >
                        <X aria-hidden="true" className="h-4 w-4" />
                    </Button>
                </div>
            ))}
        </div>
    );
}
