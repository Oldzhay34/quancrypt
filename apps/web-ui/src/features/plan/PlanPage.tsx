import { useState } from 'react';
import { errorMessageKey } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { ScanGate } from '@/shared/scan';
import { ErrorBanner, Page, Spinner } from '@/shared/ui';
import { PlanTable } from './components/PlanTable';
import { ReportView } from './components/ReportView';
import { useApprove, usePlan } from './hooks';
import styles from './Plan.module.css';

type Tab = 'items' | 'report';

/** The migration plan of the newest completed scan (UC3): items in risk order, the report, and approving an item. */
export function PlanPage() {
    const { t } = useI18n();
    const { project } = useProject();
    if (!project) return null;
    return (
        <Page title={t('nav.plan')} wide>
            <ScanGate projectId={project.id}>{(scan) => <Plan key={scan.id} scanId={scan.id} />}</ScanGate>
        </Page>
    );
}

function Plan({ scanId }: { scanId: string }) {
    const { t } = useI18n();
    const [tab, setTab] = useState<Tab>('items');
    const { plan, findings, rows } = usePlan(scanId);
    const approve = useApprove(scanId);
    return (
        <>
            <div role="tablist" aria-label={t('plan.tabs')} className={`${styles.tabs} ${styles.noPrint}`}>
                {(['items', 'report'] as const).map((id) => (
                    <button
                        key={id}
                        type="button"
                        role="tab"
                        id={`plan-tab-${id}`}
                        aria-selected={tab === id}
                        aria-controls={`plan-panel-${id}`}
                        className={tab === id ? styles.tabActive : styles.tab}
                        onClick={() => setTab(id)}
                    >
                        {t(id === 'items' ? 'plan.tab.items' : 'plan.tab.report')}
                    </button>
                ))}
            </div>
            <div role="tabpanel" id={`plan-panel-${tab}`} aria-labelledby={`plan-tab-${tab}`}>
                {tab === 'report' ? (
                    <ReportView scanId={scanId} />
                ) : plan.isPending || findings.isPending ? (
                    <Spinner label={t('common.loading')} />
                ) : plan.error || findings.error ? (
                    <ErrorBanner>{t(errorMessageKey(plan.error ?? findings.error))}</ErrorBanner>
                ) : plan.data === null || rows === null ? (
                    <p>{t('plan.none')}</p>
                ) : (
                    <>
                        {approve.isError ? (
                            <ErrorBanner>{t(errorMessageKey(approve.error))}</ErrorBanner>
                        ) : null}
                        <PlanTable
                            rows={rows}
                            approving={approve.isPending}
                            onApprove={(item) => approve.mutate(item)}
                        />
                    </>
                )}
            </div>
        </>
    );
}
