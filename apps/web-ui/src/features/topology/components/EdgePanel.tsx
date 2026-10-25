import { useI18n } from '@/shared/i18n';
import type { Connection } from '../graph';
import styles from '../Topology.module.css';
import { STATUS_LABELS } from './Legend';

/**
 * The side panel of a selected connection: protocol, TLS, mTLS, the quantum status (derived from the linked findings) and those
 * findings. The service records no key-exchange group per connection yet, so that row says so instead of guessing.
 */
export function EdgePanel({ connection, onClose }: { connection: Connection; onClose: () => void }) {
    const { t } = useI18n();
    const yes = t('common.yes');
    const no = t('common.no');
    return (
        <aside className={styles.panel} aria-label={t('topology.panel.title')}>
            <div className={styles.panelHead}>
                <h2 className={styles.panelTitle}>
                    {connection.source} → {connection.target}
                </h2>
                <button type="button" className={styles.close} onClick={onClose}>
                    {t('topology.panel.close')}
                </button>
            </div>
            <dl className={styles.facts}>
                <dt>{t('topology.panel.protocol')}</dt>
                <dd>{connection.protocol}</dd>
                <dt>TLS</dt>
                <dd>{connection.tls ? yes : no}</dd>
                <dt>mTLS</dt>
                <dd>{connection.mtls ? yes : no}</dd>
                <dt>{t('topology.panel.status')}</dt>
                <dd>{t(STATUS_LABELS[connection.status])}</dd>
                <dt>{t('topology.panel.keyExchange')}</dt>
                <dd>{t('topology.panel.keyExchange.none')}</dd>
                <dt>{t('topology.panel.callSites')}</dt>
                <dd>{connection.callSiteCount}</dd>
            </dl>
            <h3 className={styles.panelSub}>{t('topology.panel.findings')}</h3>
            {connection.findings.length === 0 ? (
                <p className={styles.note}>{t('topology.panel.noFindings')}</p>
            ) : (
                <ul className={styles.findings}>
                    {connection.findings.map((finding) => (
                        <li key={finding.id}>
                            <span className={styles.path}>
                                {finding.lineStart === null
                                    ? finding.path
                                    : `${finding.path}:${finding.lineStart}`}
                            </span>
                            <span className={styles.meta}>
                                {finding.algorithmFamily} · {finding.usageContext} · {finding.priority}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </aside>
    );
}
