import { useQuery } from '@tanstack/react-query';
import { FileCode2 } from 'lucide-react';
import { ApiError, errorMessageKey, useApi } from '@/shared/api';
import type { Finding } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { ErrorBanner, Spinner } from '@/shared/ui';
import { getSnippet } from '../api';
import { CodeBlock } from './CodeBlock';
import styles from './Findings.module.css';

/** One finding with its place and the source lines there (D-361c). A key store is never read. */
export function FindingCard({ finding, root }: { finding: Finding; root: string }) {
    const { t } = useI18n();
    const api = useApi();
    const line = finding.locationKind === 'KEYSTORE_FILE' ? null : finding.lineStart;
    const snippet = useQuery({
        queryKey: ['snippet', finding.scanId, root, finding.path, line],
        enabled: line !== null,
        queryFn: ({ signal }) => getSnippet(api, finding.scanId, root, finding.path, line as number, signal),
    });
    const place = finding.lineStart === null ? finding.path : `${finding.path}:${finding.lineStart}`;
    const withheld = snippet.error instanceof ApiError && snippet.error.status === 404;

    return (
        <article className={styles.card}>
            <header className={styles.head}>
                <span className={`${styles.priority} ${styles[finding.priority]}`}>{finding.priority}</span>
                <h3 className={styles.place}>
                    <FileCode2 aria-hidden="true" className="h-4 w-4 shrink-0" />
                    <span>{place}</span>
                </h3>
            </header>
            <p className={styles.meta}>
                <span className={styles.chip}>{finding.algorithmFamily}</span>
                <span className={styles.chip}>{finding.usageContext}</span>
                <span className={styles.symbol}>{finding.symbol}</span>
            </p>
            {line === null ? <p className={styles.note}>{t('code.wholeFile')}</p> : null}
            {line !== null && snippet.isPending ? <Spinner label={t('common.loading')} /> : null}
            {withheld ? <p className={styles.note}>{t('code.withheld')}</p> : null}
            {snippet.isError && !withheld ? (
                <ErrorBanner>{t(errorMessageKey(snippet.error))}</ErrorBanner>
            ) : null}
            {snippet.data && line !== null ? <CodeBlock snippet={snippet.data} line={line} /> : null}
        </article>
    );
}
