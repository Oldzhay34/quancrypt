import { useI18n } from '@/shared/i18n';
import type { Connection } from '../graph';
import styles from '../Topology.module.css';
import { STATUS_LABELS } from './Legend';

/** The same connections as text, reachable with the keyboard; choosing one opens the side panel like a tap on the graph. */
export function ConnectionList({
    connections,
    selectedId,
    onSelect,
}: {
    connections: Connection[];
    selectedId: string | null;
    onSelect: (id: string) => void;
}) {
    const { t } = useI18n();
    return (
        <table className={styles.list}>
            <caption>{t('topology.connections')}</caption>
            <thead>
                <tr>
                    <th scope="col">{t('topology.col.connection')}</th>
                    <th scope="col">{t('topology.panel.protocol')}</th>
                    <th scope="col">TLS</th>
                    <th scope="col">mTLS</th>
                    <th scope="col">{t('topology.panel.status')}</th>
                </tr>
            </thead>
            <tbody>
                {connections.map((connection) => (
                    <tr
                        key={connection.id}
                        className={connection.id === selectedId ? styles.selected : undefined}
                    >
                        <th scope="row">
                            <button
                                type="button"
                                className={styles.rowButton}
                                aria-pressed={connection.id === selectedId}
                                onClick={() => onSelect(connection.id)}
                            >
                                {connection.source} → {connection.target}
                            </button>
                        </th>
                        <td>{connection.protocol}</td>
                        <td>{connection.tls ? t('common.yes') : t('common.no')}</td>
                        <td>{connection.mtls ? t('common.yes') : t('common.no')}</td>
                        <td>{t(STATUS_LABELS[connection.status])}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}
