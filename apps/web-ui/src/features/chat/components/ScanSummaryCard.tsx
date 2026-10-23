import { useI18n } from '@/shared/i18n';
import type { ScanOverview } from '../hooks';
import styles from './Scan.module.css';

const PRIORITIES = ['P0', 'P1', 'P2', 'P3'] as const;

function whenText(iso: string | null, language: string): string | null {
    if (iso === null) return null;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return null;
    return new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

/** The initial scan's result (UC1): findings by algorithm family and priority, and the size of the service graph. */
export function ScanSummaryCard({ overview }: { overview: ScanOverview }) {
    const { t, language } = useI18n();
    const { summary, topology } = overview;
    const families = Object.entries(summary.countsByAlgorithmFamily).sort(
        ([nameA, countA], [nameB, countB]) => countB - countA || nameA.localeCompare(nameB),
    );
    const completed = whenText(summary.scan.completedAt, language);
    return (
        <section className={styles.summary} aria-labelledby="scan-summary-title">
            <h3 id="scan-summary-title" className={styles.summaryTitle}>
                {t('chat.summary.title')}
            </h3>
            {completed ? (
                <p className={styles.meta}>{t('chat.summary.completed', { time: completed })}</p>
            ) : null}
            <ul className={styles.counts}>
                <li>{t('chat.summary.findings', { count: summary.findingCount })}</li>
                {topology ? (
                    <>
                        <li>{t('chat.summary.nodes', { count: topology.nodes.length })}</li>
                        <li>{t('chat.summary.edges', { count: topology.links.length })}</li>
                    </>
                ) : (
                    <li>{t('chat.summary.noTopology')}</li>
                )}
            </ul>
            <div className={styles.tables}>
                <table className={styles.table}>
                    <caption>{t('chat.summary.families')}</caption>
                    <thead>
                        <tr>
                            <th scope="col">{t('chat.summary.family')}</th>
                            <th scope="col">{t('chat.summary.count')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {families.map(([family, count]) => (
                            <tr key={family}>
                                <th scope="row">{family}</th>
                                <td>{count}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                <table className={styles.table}>
                    <caption>{t('chat.summary.priorities')}</caption>
                    <thead>
                        <tr>
                            <th scope="col">{t('chat.summary.priority')}</th>
                            <th scope="col">{t('chat.summary.count')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {PRIORITIES.map((priority) => (
                            <tr key={priority}>
                                <th scope="row">{priority}</th>
                                <td>{summary.countsByPriority[priority] ?? 0}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
