import { Boxes, KeyRound, ListChecks, ScanSearch, Settings } from 'lucide-react';
import { Sidebar } from '@/components/ui/sidebar';
import { ChatHistory, NewChatButton } from '@/features/chat';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';

const ICON = 'h-5 w-5';
interface Entry {
    to: string;
    label: MessageKey;
    icon: React.ReactNode;
}
const PAGES: Entry[] = [
    { to: '/analysis', label: 'nav.analysis', icon: <ScanSearch className={ICON} /> },
    { to: '/inventory', label: 'nav.inventory', icon: <KeyRound className={ICON} /> },
    { to: '/topology', label: 'nav.topology', icon: <Boxes className={ICON} /> },
    { to: '/plan', label: 'nav.plan', icon: <ListChecks className={ICON} /> },
];
const FOOTER: Entry[] = [{ to: '/settings', label: 'nav.settings', icon: <Settings className={ICON} /> }];

export function SideNav() {
    const { t } = useI18n();
    const translate = (entry: Entry) => ({ ...entry, label: t(entry.label) });
    return (
        <Sidebar
            brand={t('app.title')}
            items={PAGES.map(translate)}
            footerItems={FOOTER.map(translate)}
            labels={{
                nav: t('nav.label'),
                open: t('nav.open'),
                close: t('nav.close'),
                collapse: t('nav.collapse'),
                expand: t('nav.expand'),
            }}
            action={(collapsed, close) => <NewChatButton collapsed={collapsed} onNavigate={close} />}
        >
            {(close) => <ChatHistory onNavigate={close} />}
        </Sidebar>
    );
}
