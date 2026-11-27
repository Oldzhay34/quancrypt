import { NavLink } from 'react-router';
import styles from './Tabs.module.css';

/** Links that switch between the parts of one screen; the current one is marked. */
export function Tabs({ label, items }: { label: string; items: { to: string; label: string }[] }) {
    return (
        <nav aria-label={label} className={styles.tabs}>
            {items.map((item) => (
                <NavLink
                    key={item.to}
                    to={item.to}
                    end
                    className={({ isActive }) => (isActive ? `${styles.tab} ${styles.active}` : styles.tab)}
                >
                    {item.label}
                </NavLink>
            ))}
        </nav>
    );
}
