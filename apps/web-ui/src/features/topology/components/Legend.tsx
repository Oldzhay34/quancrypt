import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { NODE_SHAPES } from '../graph';
import type { NodeKind } from '../graph';
import { STATUSES } from '../palette';
import type { QuantumStatus } from '../quantum';
import styles from '../Topology.module.css';

export const STATUS_LABELS: Record<QuantumStatus, MessageKey> = {
    VULNERABLE: 'topology.status.VULNERABLE',
    RESISTANT: 'topology.status.RESISTANT',
    MIXED: 'topology.status.MIXED',
    SYMMETRIC_OR_HASH: 'topology.status.SYMMETRIC_OR_HASH',
    UNKNOWN: 'topology.status.UNKNOWN',
};

export const NODE_LABELS: Record<NodeKind, MessageKey> = {
    SERVICE: 'topology.node.SERVICE',
    GATEWAY: 'topology.node.GATEWAY',
    BROKER: 'topology.node.BROKER',
    DEVICE: 'topology.node.DEVICE',
    EXTERNAL_CLIENT: 'topology.node.EXTERNAL_CLIENT',
};

/** The shape of each node kind in words (see `NODE_SHAPES`). */
const SHAPE_LABELS: Record<NodeKind, MessageKey> = {
    SERVICE: 'topology.shape.SERVICE',
    GATEWAY: 'topology.shape.GATEWAY',
    BROKER: 'topology.shape.BROKER',
    DEVICE: 'topology.shape.DEVICE',
    EXTERNAL_CLIENT: 'topology.shape.EXTERNAL_CLIENT',
};

const SWATCH: Record<QuantumStatus, string> = {
    VULNERABLE: styles.swatchVulnerable ?? '',
    RESISTANT: styles.swatchResistant ?? '',
    MIXED: styles.swatchMixed ?? '',
    SYMMETRIC_OR_HASH: styles.swatchSymmetric ?? '',
    UNKNOWN: styles.swatchUnknown ?? '',
};

/** What the colours and shapes mean. Each status has a name, so the colour is never the only way to read it. */
export function Legend() {
    const { t } = useI18n();
    return (
        <section className={styles.legend} aria-labelledby="topology-legend-title">
            <h2 id="topology-legend-title" className={styles.legendTitle}>
                {t('topology.legend.title')}
            </h2>
            <ul className={styles.legendList}>
                {STATUSES.map((status) => (
                    <li key={status}>
                        <span className={`${styles.swatch} ${SWATCH[status]}`} aria-hidden="true" />
                        {t(STATUS_LABELS[status])}
                    </li>
                ))}
            </ul>
            <ul className={styles.legendList}>
                {(Object.keys(NODE_SHAPES) as NodeKind[]).map((kind) => (
                    <li key={kind}>
                        {t(NODE_LABELS[kind])}: {t(SHAPE_LABELS[kind])}
                    </li>
                ))}
            </ul>
            <p className={styles.note}>{t('topology.legend.note')}</p>
        </section>
    );
}
