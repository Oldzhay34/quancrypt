import { useState } from 'react';
import { useNavigate } from 'react-router';
import { errorMessageKey } from '@/shared/api';
import type { Consent, ConsentType } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { useProject } from '@/shared/project';
import { ErrorBanner, Page, Spinner } from '@/shared/ui';
import { ConsentForm } from './components/ConsentForm';
import { useApplyConsents, useConsents, usePrivacyNotice } from './hooks';

type Selection = Record<ConsentType, boolean>;

/** The switches start from the consents that are really active (all off on a first run, D-21). */
function activeSelection(consents: Consent[]): Selection {
    const isActive = (type: ConsentType) =>
        consents.some((consent) => consent.consentType === type && consent.revokedAt === null);
    return {
        WAREHOUSE_ANALYTICS: isActive('WAREHOUSE_ANALYTICS'),
        MODEL_TRAINING: isActive('MODEL_TRAINING'),
    };
}

/** First run: the privacy notice and two separate consents. Continuing without any consent is allowed (D-21). */
export function ConsentPage() {
    const { t, language } = useI18n();
    const { project } = useProject();
    const projectId = project?.id ?? '';
    const notice = usePrivacyNotice();
    const consents = useConsents(projectId);

    if (notice.isError || consents.isError) return <ErrorBanner>{t('error.generic')}</ErrorBanner>;
    if (!notice.data || !consents.data) return <Spinner label={t('common.loading')} />;
    return (
        <Page title={t('consent.title')}>
            <ConsentStep
                projectId={projectId}
                existing={consents.data}
                noticeVersion={notice.data.version}
                noticeText={language === 'tr' ? notice.data.textTr : notice.data.textEn}
            />
        </Page>
    );
}

function ConsentStep(props: {
    projectId: string;
    existing: Consent[];
    noticeVersion: number;
    noticeText: string;
}) {
    const { t } = useI18n();
    const navigate = useNavigate();
    const apply = useApplyConsents(props.projectId);
    const [selection, setSelection] = useState<Selection>(() => activeSelection(props.existing));

    return (
        <ConsentForm
            noticeText={props.noticeText}
            noticeVersion={props.noticeVersion}
            selection={selection}
            onToggle={(type, value) => setSelection((current) => ({ ...current, [type]: value }))}
            onContinue={() =>
                apply.mutate(
                    { selection, noticeVersion: props.noticeVersion, existing: props.existing },
                    { onSuccess: () => void navigate('/', { replace: true }) },
                )
            }
            busy={apply.isPending}
            errorText={apply.isError ? t(errorMessageKey(apply.error)) : null}
        />
    );
}
