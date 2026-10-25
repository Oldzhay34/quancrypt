import type { Finding } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import styles from '../Inventory.module.css';

function location(finding: Finding): string {
    return finding.lineStart === null ? finding.path : `${finding.path}:${finding.lineStart}`;
}

/** The findings of one page: file and line are text, never links; the codes are the contract's. */
export function FindingsTable({ rows, total }: { rows: Finding[]; total: number }) {
    const { t } = useI18n();
    return (
        <div className={styles.tableWrap}>
            <table className={styles.table}>
                <caption>{t('inventory.table.caption', { count: total })}</caption>
                <thead>
                    <tr>
                        <th scope="col">{t('inventory.col.priority')}</th>
                        <th scope="col">{t('inventory.col.algorithm')}</th>
                        <th scope="col">{t('inventory.col.usage')}</th>
                        <th scope="col">{t('inventory.col.location')}</th>
                        <th scope="col">{t('inventory.col.symbol')}</th>
                        <th scope="col">{t('inventory.col.kind')}</th>
                        <th scope="col">{t('inventory.col.keyBits')}</th>
                        <th scope="col">{t('inventory.col.classifiedBy')}</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((finding) => (
                        <tr key={finding.id}>
                            <td>{finding.priority}</td>
                            <td>{finding.algorithmFamily}</td>
                            <td>{finding.usageContext}</td>
                            <td className={styles.path}>{location(finding)}</td>
                            <td className={styles.path}>{finding.symbol}</td>
                            <td>{finding.locationKind}</td>
                            <td>{finding.keySizeBits ?? '—'}</td>
                            <td>{finding.classifiedBy}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
