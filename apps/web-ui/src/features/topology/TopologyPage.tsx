import { errorMessageKey } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { ScanGate } from '@/shared/scan';
import { ErrorBanner, Page, Spinner } from '@/shared/ui';
import { ConnectionList } from './components/ConnectionList';
import { EdgePanel } from './components/EdgePanel';
import { Legend } from './components/Legend';
import { TopologyGraphView } from './components/TopologyGraphView';
import { useTopologyGraph } from './hooks';
import styles from './Topology.module.css';

/** The service graph of the newest completed scan (UC3): nodes by kind, connections coloured by quantum status, a legend. */
export function TopologyPage() {
    const { t } = useI18n();
    const { project } = useProject();
    if (!project) return null;
    return (
        <Page title={t('nav.topology')} wide>
            <ScanGate projectId={project.id}>
                {(scan) => <Topology key={scan.id} scanId={scan.id} />}
            </ScanGate>
        </Page>
    );
}

function Topology({ scanId }: { scanId: string }) {
    const { t } = useI18n();
    const { topology, findings, graph, selected, selectedId, setSelectedId } = useTopologyGraph(scanId);
    if (topology.isPending || findings.isPending) return <Spinner label={t('common.loading')} />;
    const error = topology.error ?? findings.error;
    if (error) return <ErrorBanner>{t(errorMessageKey(error))}</ErrorBanner>;
    if (topology.data === null || graph === null) return <p>{t('topology.none')}</p>;
    return (
        <>
            <div className={styles.layout}>
                <div className={styles.main}>
                    <TopologyGraphView
                        graph={graph}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        label={t('topology.graph.label')}
                    />
                </div>
                {selected ? <EdgePanel connection={selected} onClose={() => setSelectedId(null)} /> : null}
            </div>
            <Legend />
            <ConnectionList
                connections={graph.connections}
                selectedId={selectedId}
                onSelect={setSelectedId}
            />
        </>
    );
}
