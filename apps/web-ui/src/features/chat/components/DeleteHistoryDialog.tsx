import { useI18n } from '@/shared/i18n';
import { Button, Dialog } from '@/shared/ui';

/** "Delete history" asks first: the chat messages of the project are removed for good. */
export function DeleteHistoryDialog({
    busy,
    onConfirm,
    onClose,
}: {
    busy: boolean;
    onConfirm: () => void;
    onClose: () => void;
}) {
    const { t } = useI18n();
    return (
        <Dialog
            title={t('chat.history.delete.title')}
            onClose={onClose}
            actions={
                <>
                    <Button onClick={onClose} disabled={busy}>
                        {t('common.cancel')}
                    </Button>
                    <Button variant="danger" onClick={onConfirm} disabled={busy}>
                        {busy ? t('chat.history.deleting') : t('chat.history.delete')}
                    </Button>
                </>
            }
        >
            <p>{t('chat.history.delete.body')}</p>
        </Dialog>
    );
}
