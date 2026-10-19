import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import styles from './Dialog.module.css';

interface DialogProps {
    title: string;
    children: ReactNode;
    actions: ReactNode;
    onClose: () => void;
}

/** A small modal: focus moves into it, Escape closes it, focus returns to the opener. */
export function Dialog({ title, children, actions, onClose }: DialogProps) {
    const titleId = useId();
    const panel = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        panel.current?.focus();
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('keydown', onKey);
            opener?.focus();
        };
    }, [onClose]);

    return (
        <div className={styles.backdrop}>
            <div
                ref={panel}
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                tabIndex={-1}
                className={styles.panel}
            >
                <h2 id={titleId} className={styles.title}>
                    {title}
                </h2>
                <div>{children}</div>
                <div className={styles.actions}>{actions}</div>
            </div>
        </div>
    );
}
