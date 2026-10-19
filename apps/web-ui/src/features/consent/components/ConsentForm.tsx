import { Button, ErrorBanner, Switch } from '@/shared/ui';
import { CONSENT_TYPES } from '@/shared/api';
import type { ConsentType } from '@/shared/api';
import { useI18n } from '@/shared/i18n';
import { NoticeText } from './NoticeText';
import styles from './ConsentForm.module.css';

interface ConsentFormProps {
    noticeText: string;
    noticeVersion: number;
    selection: Record<ConsentType, boolean>;
    onToggle: (type: ConsentType, value: boolean) => void;
    onContinue: () => void;
    busy: boolean;
    errorText: string | null;
}

/** Presentation only: both switches are controlled, the container decides what "Continue" does. */
export function ConsentForm({
    noticeText,
    noticeVersion,
    selection,
    onToggle,
    onContinue,
    busy,
    errorText,
}: ConsentFormProps) {
    const { t } = useI18n();
    return (
        <form
            onSubmit={(event) => {
                event.preventDefault();
                onContinue();
            }}
        >
            <p>{t('consent.intro')}</p>
            <h2>{t('consent.notice.version', { version: noticeVersion })}</h2>
            <NoticeText text={noticeText} />
            <p>
                <small>{t('consent.notice.disclaimer')}</small>
            </p>
            <fieldset className={styles.fieldset} disabled={busy}>
                {CONSENT_TYPES.map((type) => (
                    <Switch
                        key={type}
                        id={`consent-${type}`}
                        checked={selection[type]}
                        onChange={(value) => onToggle(type, value)}
                        label={t(`consent.${type}.title`)}
                        description={t(`consent.${type}.desc`)}
                        stateLabel={t(selection[type] ? 'consent.state.on' : 'consent.state.off')}
                    />
                ))}
            </fieldset>
            <p>{t('consent.withoutConsentHint')}</p>
            {errorText ? <ErrorBanner>{errorText}</ErrorBanner> : null}
            <Button type="submit" variant="primary" disabled={busy}>
                {busy ? t('consent.saving') : t('consent.continue')}
            </Button>
        </form>
    );
}
