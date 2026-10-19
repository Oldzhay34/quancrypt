import { useI18n } from '../i18n/I18nProvider';
import { Page } from '../ui';

/** Shown when the page was opened without a session token. */
export function NoTokenScreen() {
    const { t } = useI18n();
    return (
        <Page title={t('auth.missing.title')}>
            <p>{t('auth.missing.body')}</p>
        </Page>
    );
}

/** Shown after a 401: the services refused the token. */
export function SessionInvalidScreen() {
    const { t } = useI18n();
    return (
        <Page title={t('auth.rejected.title')}>
            <p>{t('auth.rejected.body')}</p>
        </Page>
    );
}
