import { Link } from 'react-router';
import { useI18n } from '@/shared/i18n';

/** The empty conversation (adapted from the given bolt-style screen): a title above the message box. */
export function EmptyHero({ needsScan }: { needsScan: boolean }) {
    const { t } = useI18n();
    return (
        <div className="flex flex-col items-center px-4 pb-2 text-center">
            <h2 className="m-0 text-3xl font-semibold tracking-tight">{t('chat.hero.title')}</h2>
            <p className="mt-2 mb-0 max-w-md text-sm text-muted-foreground">{t('chat.empty')}</p>
            {needsScan ? (
                <p className="mt-2 mb-0 text-sm">
                    <Link to="/analysis">{t('chat.hero.scanFirst')}</Link>
                </p>
            ) : null}
        </div>
    );
}
