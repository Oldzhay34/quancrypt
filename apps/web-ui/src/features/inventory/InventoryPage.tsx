import { errorMessageKey } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { ScanGate } from '@/shared/scan';
import { Button, ErrorBanner, Page, Spinner } from '@/shared/ui';
import { FindingFilters } from './components/FindingFilters';
import { FindingsTable } from './components/FindingsTable';
import { SummaryStrip } from './components/SummaryStrip';
import { useCbomDownload, useInventory, useScanSummary } from './hooks';
import styles from './Inventory.module.css';

/** The inventory (UC3): counts, filters, the findings of the newest completed scan, and the CBOM download. */
export function InventoryPage() {
    const { t } = useI18n();
    const { project } = useProject();
    if (!project) return null;
    return (
        <Page title={t('nav.inventory')} wide>
            <ScanGate projectId={project.id}>
                {(scan) => <Inventory key={scan.id} scanId={scan.id} />}
            </ScanGate>
        </Page>
    );
}

function Inventory({ scanId }: { scanId: string }) {
    const { t } = useI18n();
    const summary = useScanSummary(scanId);
    const inventory = useInventory(scanId);
    const cbom = useCbomDownload(scanId);
    const { findings } = inventory;
    return (
        <>
            {summary.data ? <SummaryStrip summary={summary.data} /> : null}
            {summary.isError ? <ErrorBanner>{t(errorMessageKey(summary.error))}</ErrorBanner> : null}
            <div className={styles.toolbar}>
                <FindingFilters filter={inventory.filter} onChange={inventory.setFilter} />
                <span className={styles.spacer} />
                <Button onClick={() => cbom.mutate()} disabled={cbom.isPending}>
                    {t('inventory.cbom')}
                </Button>
            </div>
            {cbom.data === 'missing' ? <p role="status">{t('inventory.cbom.missing')}</p> : null}
            {cbom.isError ? <ErrorBanner>{t(errorMessageKey(cbom.error))}</ErrorBanner> : null}
            {findings.isPending ? <Spinner label={t('common.loading')} /> : null}
            {findings.isError ? <ErrorBanner>{t(errorMessageKey(findings.error))}</ErrorBanner> : null}
            {findings.data ? (
                inventory.total === 0 ? (
                    <p className={styles.note}>{t('inventory.empty')}</p>
                ) : (
                    <>
                        <FindingsTable rows={inventory.rows} total={inventory.total} />
                        <nav className={styles.pager} aria-label={t('inventory.pager')}>
                            <Button
                                disabled={inventory.page === 0}
                                onClick={() => inventory.setPage(inventory.page - 1)}
                            >
                                {t('inventory.prev')}
                            </Button>
                            <span>
                                {t('inventory.page', { page: inventory.page + 1, pages: inventory.pages })}
                            </span>
                            <Button
                                disabled={inventory.page >= inventory.pages - 1}
                                onClick={() => inventory.setPage(inventory.page + 1)}
                            >
                                {t('inventory.next')}
                            </Button>
                        </nav>
                    </>
                )
            ) : null}
        </>
    );
}
