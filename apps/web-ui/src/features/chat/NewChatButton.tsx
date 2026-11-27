import { SquarePen } from 'lucide-react';
import { useNavigate } from 'react-router';
import { cn } from '@/lib/utils';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { useChatRuns } from './runs';

/** Opens an empty chat from anywhere in the app. */
export function NewChatButton({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
    const { t } = useI18n();
    const { project } = useProject();
    const { select } = useChatRuns();
    const navigate = useNavigate();
    return (
        <button
            type="button"
            title={t('chat.sessions.new')}
            disabled={!project}
            onClick={() => {
                if (!project) return;
                select(project.id, null);
                onNavigate?.();
                void navigate('/chat');
            }}
            className="mb-1 flex shrink-0 cursor-pointer items-center gap-3 overflow-hidden rounded-lg border border-border bg-transparent px-2 py-2 text-left font-[inherit] text-sm whitespace-nowrap text-foreground hover:bg-accent"
        >
            <SquarePen aria-hidden="true" className="h-5 w-5 shrink-0" />
            <span className={cn(collapsed && 'md:sr-only')}>{t('chat.sessions.new')}</span>
        </button>
    );
}
