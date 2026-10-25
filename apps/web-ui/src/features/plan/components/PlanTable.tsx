import { useState } from 'react';
import type { PlanItem } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { Button, Dialog } from '@/shared/ui';
import type { PlanRow } from '../hooks';
import styles from '../Plan.module.css';

const RISK_CLASS_STYLE: Record<PlanItem['riskClass'], string | undefined> = {
    CRITICAL: styles.critical,
    HIGH: styles.high,
    MEDIUM: styles.medium,
    LOW: styles.low,
};

const STATE_LABELS: Record<PlanItem['state'], MessageKey> = {
    DISCOVERED: 'plan.state.DISCOVERED',
    PLANNED: 'plan.state.PLANNED',
    APPROVED: 'plan.state.APPROVED',
    APPLIED: 'plan.state.APPLIED',
    VERIFIED: 'plan.state.VERIFIED',
    ROLLED_BACK: 'plan.state.ROLLED_BACK',
};

function Reasons({ item }: { item: PlanItem }) {
    const { t } = useI18n();
    if (item.riskFactors.length === 0) return <span className={styles.muted}>{t('plan.reasons.none')}</span>;
    return (
        <details>
            <summary>{t('plan.reasons.count', { count: item.riskFactors.length })}</summary>
            <ol className={styles.reasons}>
                {item.riskFactors.map((factor, index) => (
                    <li key={index}>
                        {factor.featureName}: {factor.shapValue.toFixed(3)}
                    </li>
                ))}
            </ol>
        </details>
    );
}

/** The plan items in risk order: priority, strategy, effort, risk class, reasons, state badge and, for a planned item, "Approve". */
export function PlanTable({
    rows,
    approving,
    onApprove,
}: {
    rows: PlanRow[];
    approving: boolean;
    onApprove: (item: PlanItem) => void;
}) {
    const { t } = useI18n();
    const [confirming, setConfirming] = useState<PlanRow | null>(null);
    return (
        <>
            <div className={styles.tableWrap}>
                <table className={styles.table}>
                    <caption>{t('plan.table.caption', { count: rows.length })}</caption>
                    <thead>
                        <tr>
                            <th scope="col">#</th>
                            <th scope="col">{t('plan.col.finding')}</th>
                            <th scope="col">{t('plan.col.priority')}</th>
                            <th scope="col">{t('plan.col.strategy')}</th>
                            <th scope="col">{t('plan.col.effort')}</th>
                            <th scope="col">{t('plan.col.risk')}</th>
                            <th scope="col">{t('plan.col.reasons')}</th>
                            <th scope="col">{t('plan.col.state')}</th>
                            <th scope="col" className={styles.noPrint}>
                                <span className={styles.srOnly}>{t('plan.col.actions')}</span>
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, index) => (
                            <tr key={row.item.id}>
                                <td>{index + 1}</td>
                                <td className={styles.path}>
                                    {row.finding
                                        ? `${row.finding.path}${row.finding.lineStart === null ? '' : `:${row.finding.lineStart}`}`
                                        : row.item.findingId}
                                    {row.finding ? (
                                        <div className={styles.muted}>{row.finding.symbol}</div>
                                    ) : null}
                                </td>
                                <td>{row.finding?.priority ?? '—'}</td>
                                <td>{row.item.strategy}</td>
                                <td>{row.item.effort}</td>
                                <td>
                                    {row.item.riskScore.toFixed(2)}{' '}
                                    <span
                                        className={`${styles.badge} ${RISK_CLASS_STYLE[row.item.riskClass] ?? ''}`}
                                    >
                                        {row.item.riskClass}
                                    </span>
                                </td>
                                <td>
                                    <Reasons item={row.item} />
                                </td>
                                <td>
                                    <span className={`${styles.badge} ${styles.state}`}>
                                        {t(STATE_LABELS[row.item.state])}
                                    </span>
                                </td>
                                <td className={styles.noPrint}>
                                    {row.item.state === 'PLANNED' ? (
                                        <Button disabled={approving} onClick={() => setConfirming(row)}>
                                            {t('plan.approve')}
                                        </Button>
                                    ) : null}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {confirming ? (
                <Dialog
                    title={t('plan.approve.title')}
                    onClose={() => setConfirming(null)}
                    actions={
                        <>
                            <Button onClick={() => setConfirming(null)}>{t('common.cancel')}</Button>
                            <Button
                                variant="primary"
                                onClick={() => {
                                    onApprove(confirming.item);
                                    setConfirming(null);
                                }}
                            >
                                {t('plan.approve')}
                            </Button>
                        </>
                    }
                >
                    <p>{t('plan.approve.body')}</p>
                    <p className={styles.path}>
                        {confirming.finding?.path ?? confirming.item.findingId}
                        {confirming.finding ? ` — ${confirming.finding.symbol}` : ''}
                    </p>
                </Dialog>
            ) : null}
        </>
    );
}
