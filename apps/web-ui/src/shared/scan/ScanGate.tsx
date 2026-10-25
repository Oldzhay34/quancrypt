import type { ReactNode } from 'react';
import { errorMessageKey } from '@/shared/api';
import type { Scan } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { ErrorBanner, Spinner } from '@/shared/ui';
import { useLatestCompletedScan } from './useLatestCompletedScan';

/**
 * What the inventory, topology and plan screens have in common: they show the newest completed scan of the project. While it
 * loads, when it failed to load and when the project was never scanned, this explains it; otherwise it renders the screen.
 */
export function ScanGate({
    projectId,
    children,
}: {
    projectId: string;
    children: (scan: Scan) => ReactNode;
}) {
    const { t } = useI18n();
    const latest = useLatestCompletedScan(projectId);
    if (latest.isPending) return <Spinner label={t('common.loading')} />;
    if (latest.isError) return <ErrorBanner>{t(errorMessageKey(latest.error))}</ErrorBanner>;
    if (latest.data === null) return <p>{t('scan.none')}</p>;
    return <>{children(latest.data)}</>;
}
