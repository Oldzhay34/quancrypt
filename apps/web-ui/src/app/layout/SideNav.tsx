import { NavLink } from 'react-router';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import styles from './Layout.module.css';

const ITEMS: { to: string; label: MessageKey }[] = [
    { to: '/chat', label: 'nav.chat' },
    { to: '/inventory', label: 'nav.inventory' },
    { to: '/topology', label: 'nav.topology' },
    { to: '/plan', label: 'nav.plan' },
    { to: '/settings', label: 'nav.settings' },
];

export function SideNav() {
    const { t } = useI18n();
    return (
        <nav aria-label={t('nav.label')} className={styles.nav}>
            {ITEMS.map((item) => (
                <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) => (isActive ? styles.active : styles.link)}
                >
                    {t(item.label)}
                </NavLink>
            ))}
        </nav>
    );
}
