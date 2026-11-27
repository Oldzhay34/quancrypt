import { CreditCard, Gauge, Settings, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { useI18n } from '@/shared/i18n';
import type { Language, MessageKey } from '@/shared/i18n';

const ICON = 'h-4 w-4';
// The consent management is the settings page itself, so "Consents" and "Settings" open the same screen (P5.6 plan).
const ENTRIES: { to: string; label: MessageKey; icon: React.ReactNode }[] = [
    { to: '/settings', label: 'menu.consents', icon: <ShieldCheck aria-hidden="true" className={ICON} /> },
    { to: '/settings/usage', label: 'menu.usage', icon: <Gauge aria-hidden="true" className={ICON} /> },
    {
        to: '/subscription',
        label: 'menu.subscription',
        icon: <CreditCard aria-hidden="true" className={ICON} />,
    },
    { to: '/settings', label: 'nav.settings', icon: <Settings aria-hidden="true" className={ICON} /> },
];

/** The menu that opens from "Settings" at the bottom of the sidebar (D-358c); the language is chosen here (D-360b). */
export function SettingsMenu({ collapsed, onNavigate }: { collapsed: boolean; onNavigate: () => void }) {
    const { t, language, setLanguage } = useI18n();
    return (
        <DropdownMenu>
            <DropdownMenuTrigger
                title={t('nav.settings')}
                className="flex shrink-0 cursor-pointer items-center gap-3 overflow-hidden rounded-lg border-0 bg-transparent px-2 py-2 text-left font-[inherit] text-sm whitespace-nowrap text-foreground hover:bg-accent data-[state=open]:bg-accent"
            >
                <Settings aria-hidden="true" className="h-5 w-5 shrink-0" />
                <span className={cn(collapsed && 'md:sr-only')}>{t('nav.settings')}</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="top" align="start">
                {ENTRIES.map((entry) => (
                    <DropdownMenuItem key={entry.label} asChild>
                        <Link to={entry.to} onClick={onNavigate}>
                            {entry.icon}
                            {t(entry.label)}
                        </Link>
                    </DropdownMenuItem>
                ))}
                <DropdownMenuLabel>{t('lang.label')}</DropdownMenuLabel>
                <DropdownMenuRadioGroup
                    value={language}
                    onValueChange={(value) => setLanguage(value as Language)}
                >
                    <DropdownMenuRadioItem value="tr">Türkçe</DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="en">English</DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
