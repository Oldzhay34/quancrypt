import type { ReactNode } from 'react';
import styles from './ErrorBanner.module.css';

export function ErrorBanner({ children, action }: { children: ReactNode; action?: ReactNode }) {
    return (
        <div role="alert" className={styles.banner}>
            <span>{children}</span>
            {action}
        </div>
    );
}
