import { useState } from 'react';
import { errorMessageKey } from '@/shared/api';
import type { Finding } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { useScanFindings } from '@/shared/scan';
import { Button, ErrorBanner, Spinner } from '@/shared/ui';
import { FindingCard } from './FindingCard';
import styles from './Findings.module.css';

const PAGE = 10;
const byUrgency = (a: Finding, b: Finding) =>
    a.priority.localeCompare(b.priority) ||
    a.path.localeCompare(b.path) ||
    (a.lineStart ?? 0) - (b.lineStart ?? 0);

/** The scan's findings, most urgent first, ten at a time: the code is only asked for what is shown. */
export function FindingList({ scanId, root }: { scanId: string; root: string }) {
    const { t } = useI18n();
    const findings = useScanFindings(scanId);
    const [shown, setShown] = useState(PAGE);
    const sorted = [...(findings.data ?? [])].sort(byUrgency);

    return (
        <section aria-labelledby="findings-title" className={styles.list}>
            <h2 id="findings-title" className={styles.title}>
                {t('code.findings')}
            </h2>
            {findings.isPending ? <Spinner label={t('common.loading')} /> : null}
            {findings.isError ? <ErrorBanner>{t(errorMessageKey(findings.error))}</ErrorBanner> : null}
            {sorted.slice(0, shown).map((finding) => (
                <FindingCard key={finding.id} finding={finding} root={root} />
            ))}
            {sorted.length > shown ? (
                <Button onClick={() => setShown((count) => count + PAGE)}>
                    {t('code.more', { count: String(sorted.length - shown) })}
                </Button>
            ) : null}
        </section>
    );
}
