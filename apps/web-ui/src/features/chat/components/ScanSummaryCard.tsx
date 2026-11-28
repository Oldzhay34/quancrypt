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

/** A count in a table row with a bar that compares it with the largest one. */
function Row({ name, count, most }: { name: string; count: number; most: number }) {
    return (
        <tr>
            <th scope="row">{name}</th>
            <td className={styles.barCell} aria-hidden="true">
                <span className={styles.bar} style={{ width: `${most === 0 ? 0 : (count / most) * 100}%` }} />
            </td>
            <td>{count}</td>
        </tr>
    );
}

/** The scan's result (UC1): the size of the findings and the service graph, and the findings by priority and family. */
export function ScanSummaryCard({ overview }: { overview: ScanOverview }) {
    const { t, language } = useI18n();
    const { summary, topology } = overview;
    const families = Object.entries(summary.countsByAlgorithmFamily).sort(
        ([nameA, countA], [nameB, countB]) => countB - countA || nameA.localeCompare(nameB),
    );
    const priorities = PRIORITIES.map(
        (priority) => [priority, summary.countsByPriority[priority] ?? 0] as const,
    );
    const most = (rows: readonly (readonly [string, number])[]) =>
        Math.max(0, ...rows.map(([, count]) => count));
    const completed = whenText(summary.scan.completedAt, language);

    const table = (caption: string, heading: string, rows: readonly (readonly [string, number])[]) => (
        <table className={styles.table}>
            <caption>{caption}</caption>
            <thead>
                <tr>
                    <th scope="col">{heading}</th>
                    <td aria-hidden="true" />
                    <th scope="col">{t('chat.summary.count')}</th>
                </tr>
            </thead>
            <tbody>
                {rows.map(([name, count]) => (
                    <Row key={name} name={name} count={count} most={most(rows)} />
                ))}
            </tbody>
        </table>
    );

    return (
        <section className={styles.summary} aria-labelledby="scan-summary-title">
            <h2 id="scan-summary-title" className={styles.summaryTitle}>
                {t('chat.summary.title')}
            </h2>
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
                {table(t('chat.summary.priorities'), t('chat.summary.priority'), priorities)}
                {table(t('chat.summary.families'), t('chat.summary.family'), families)}
            </div>
        </section>
    );
}
