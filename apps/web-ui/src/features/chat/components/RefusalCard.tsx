import { useI18n } from '@/shared/i18n';
import styles from './Chat.module.css';

/** The fixed refusal of an out-of-scope request (UC5): the service's own sentence, shown as it is. */
export function RefusalCard({ message }: { message: string }) {
    const { t } = useI18n();
    return (
        <div role="note" className={styles.refusal}>
            <h4 className={styles.refusalTitle}>{t('chat.refusal.title')}</h4>
            <p className={styles.refusalText}>{message}</p>
        </div>
    );
}
