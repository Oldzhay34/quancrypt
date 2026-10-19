import { useI18n } from '@/shared/i18n';
import { Page } from '@/shared/ui';

/** Placeholder: the content of this screen is written in P5.3 / P5.4. */
export function ChatPage() {
    const { t } = useI18n();
    return (
        <Page title={t('nav.chat')}>
            <p>{t('placeholder.comingSoon')}</p>
        </Page>
    );
}
