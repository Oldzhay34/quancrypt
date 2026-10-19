import { useCallback, useState } from 'react';
import { errorMessageKey, CONSENT_TYPES } from '@/shared/api';
import type { ConsentType } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { Button, ErrorBanner, Page, Spinner } from '@/shared/ui';
import {
    NoticeText,
    useConsents,
    useGrantConsents,
    usePrivacyNotice,
    useRevokeConsent,
} from '@/features/consent';
import { ConsentSettings } from './components/ConsentSettings';
import type { ConsentRow } from './components/ConsentSettings';
import { RevokeDialog } from './components/RevokeDialog';

/** UC6: see the consents and withdraw (or give) them. */
export function SettingsPage() {
    const { t, language } = useI18n();
    const { project } = useProject();
    const projectId = project?.id ?? '';
    const notice = usePrivacyNotice();
    const consents = useConsents(projectId);
    const grant = useGrantConsents(projectId);
    const revoke = useRevokeConsent(projectId);
    const [pending, setPending] = useState<ConsentType | null>(null);
    const [noticeShown, setNoticeShown] = useState(false);
    const closeDialog = useCallback(() => setPending(null), []);

    if (notice.isError || consents.isError) return <ErrorBanner>{t('error.generic')}</ErrorBanner>;
    if (!notice.data || !consents.data) return <Spinner label={t('common.loading')} />;
    const existing = consents.data;
    const rows: ConsentRow[] = CONSENT_TYPES.map((type) => ({
        type,
        active: existing.some((consent) => consent.consentType === type && consent.revokedAt === null),
    }));
    const failure = grant.error ?? revoke.error;

    const confirmRevoke = () => {
        const current = existing.find((consent) => consent.consentType === pending);
        if (!pending || !current) return;
        revoke.mutate({ type: pending, version: current.version }, { onSettled: closeDialog });
    };

    return (
        <Page title={t('settings.title')}>
            <h2>{t('settings.consents.title')}</h2>
            <p>{t('settings.consents.help')}</p>
            {failure ? <ErrorBanner>{t(errorMessageKey(failure))}</ErrorBanner> : null}
            <ConsentSettings
                rows={rows}
                busy={grant.isPending || revoke.isPending}
                onEnable={(type) =>
                    grant.mutate({ types: [type], noticeVersion: notice.data.version, existing })
                }
                onDisable={setPending}
            />
            <p>
                <Button onClick={() => setNoticeShown((shown) => !shown)}>
                    {t(noticeShown ? 'settings.notice.hide' : 'settings.notice.link')}
                </Button>
            </p>
            {noticeShown ? (
                <NoticeText text={language === 'tr' ? notice.data.textTr : notice.data.textEn} />
            ) : null}
            {pending ? (
                <RevokeDialog
                    type={pending}
                    busy={revoke.isPending}
                    onConfirm={confirmRevoke}
                    onCancel={closeDialog}
                />
            ) : null}
        </Page>
    );
}
