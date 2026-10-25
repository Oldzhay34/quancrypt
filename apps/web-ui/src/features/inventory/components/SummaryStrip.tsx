import type { ScanSummary } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import styles from '../Inventory.module.css';
import { LOCATION_KINDS, PRIORITIES } from '../filters';

function Item({ label, value }: { label: string; value: number }) {
    return (
        <li>
            <span className={styles.summaryLabel}>{label}</span>
            <span className={styles.summaryValue}>{value}</span>
        </li>
    );
}

/** The counts above the table: all findings, by priority, and by location kind. */
export function SummaryStrip({ summary }: { summary: ScanSummary }) {
    const { t } = useI18n();
    return (
        <ul className={styles.summary} aria-label={t('inventory.summary')}>
            <Item label={t('inventory.summary.total')} value={summary.findingCount} />
            {PRIORITIES.map((priority) => (
                <Item key={priority} label={priority} value={summary.countsByPriority[priority] ?? 0} />
            ))}
            {LOCATION_KINDS.filter((kind) => (summary.countsByLocationKind[kind] ?? 0) > 0).map((kind) => (
                <Item key={kind} label={kind} value={summary.countsByLocationKind[kind] ?? 0} />
            ))}
        </ul>
    );
}
