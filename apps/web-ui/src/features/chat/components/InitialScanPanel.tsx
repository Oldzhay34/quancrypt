import { useId, useState } from 'react';
import type { FormEvent } from 'react';
import { errorMessageKey } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { Button, ErrorBanner, Spinner } from '@/shared/ui';
import type { ScanOverview } from '../hooks';
import { isValidRoot, MAX_ROOT_LENGTH } from '../root';
import styles from './Scan.module.css';

interface InitialScanPanelProps {
    /** The newest completed scan, null when there is none, undefined while it loads. */
    overview: ScanOverview | null | undefined;
    loadError: unknown;
    /** A turn is running: starting waits. */
    busy: boolean;
    /** The running turn is the scan. */
    scanning: boolean;
    onStart: (root: string) => void;
    /** What the box starts with: the root the project was last scanned with. */
    initialRoot: string;
    /** Read the shown code below the typed root (D-362a). */
    onShowCode: (root: string) => void;
}

/** UC1: the analysis root and the button that starts a scan. The root is remembered per project (D-362a). */
export function InitialScanPanel(props: InitialScanPanelProps) {
    const { overview, loadError, busy, scanning, onStart, initialRoot, onShowCode } = props;
    const { t } = useI18n();
    const [root, setRoot] = useState(initialRoot);
    const [invalid, setInvalid] = useState(false);
    const fieldId = useId();
    const helpId = useId();
    const errorId = useId();

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (busy) return;
        withValidRoot(onStart);
    };
    const withValidRoot = (then: (value: string) => void) => {
        const value = root.trim();
        if (!isValidRoot(value)) {
            setInvalid(true);
            return;
        }
        setInvalid(false);
        then(value);
    };

    return (
        <section className={styles.panel} aria-labelledby={`${fieldId}-title`}>
            <h2 id={`${fieldId}-title`} className={styles.title}>
                {t('chat.scan.title')}
            </h2>
            {loadError ? <ErrorBanner>{t(errorMessageKey(loadError))}</ErrorBanner> : null}
            {overview === undefined && !loadError ? <Spinner label={t('chat.summary.loading')} /> : null}
            {overview === null ? <p className={styles.none}>{t('chat.scan.none')}</p> : null}
            <form className={styles.form} onSubmit={submit} noValidate>
                <div className={styles.field}>
                    <label htmlFor={fieldId}>{t('chat.scan.rootLabel')}</label>
                    <input
                        id={fieldId}
                        type="text"
                        value={root}
                        maxLength={MAX_ROOT_LENGTH}
                        spellCheck={false}
                        autoComplete="off"
                        aria-invalid={invalid}
                        aria-describedby={invalid ? `${helpId} ${errorId}` : helpId}
                        onChange={(event) => {
                            setRoot(event.target.value);
                            setInvalid(false);
                        }}
                    />
                    <p id={helpId} className={styles.help}>
                        {t('chat.scan.rootHelp')}
                    </p>
                    {invalid ? (
                        <p id={errorId} role="alert" className={styles.error}>
                            {t('chat.scan.rootInvalid')}
                        </p>
                    ) : null}
                </div>
                <Button type="submit" variant="primary" disabled={busy}>
                    {overview ? t('chat.scan.restart') : t('chat.scan.start')}
                </Button>
                {overview ? (
                    <Button onClick={() => withValidRoot(onShowCode)}>{t('code.showWithRoot')}</Button>
                ) : null}
            </form>
            {scanning ? <Spinner label={t('chat.scan.running')} /> : null}
        </section>
    );
}
