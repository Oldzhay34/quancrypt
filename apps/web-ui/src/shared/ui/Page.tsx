import type { ReactNode } from 'react';
import styles from './Page.module.css';

/** A screen with its title. `wide` lifts the reading-width limit for tables and graphs. */
export function Page({
    title,
    wide = false,
    children,
}: {
    title: string;
    wide?: boolean;
    children: ReactNode;
}) {
    return (
        <section className={wide ? `${styles.page} ${styles.wide}` : styles.page}>
            <h1 className={styles.title}>{title}</h1>
            {children}
        </section>
    );
}
