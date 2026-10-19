import { Navigate, Outlet } from 'react-router';
import { useConsentRequired } from '@/features/consent';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { Button, ErrorBanner, Page, Spinner } from '@/shared/ui';

/** Waits for the project list; explains when there is none (run `quancrypt init`). */
export function ProjectGate() {
    const { t } = useI18n();
    const { status, retry } = useProject();
    if (status === 'loading') return <Spinner label={t('common.loading')} />;
    if (status === 'error') {
        return (
            <ErrorBanner action={<Button onClick={retry}>{t('common.retry')}</Button>}>
                {t('error.network')}
            </ErrorBanner>
        );
    }
    if (status === 'empty') {
        return (
            <Page title={t('project.none.title')}>
                <p>{t('project.none.body')}</p>
            </Page>
        );
    }
    return <Outlet />;
}

/** First run: sends to the consent screen until the notice was answered or shown (D-21). */
export function ConsentGate() {
    const { t } = useI18n();
    const { project } = useProject();
    const state = useConsentRequired(project?.id ?? '');
    if (state.error) return <ErrorBanner>{t('error.generic')}</ErrorBanner>;
    if (state.loading) return <Spinner label={t('common.loading')} />;
    if (state.required) return <Navigate to="/consent" replace />;
    return <Outlet />;
}
