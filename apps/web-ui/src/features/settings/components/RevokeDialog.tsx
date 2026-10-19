import { Button, Dialog } from '@/shared/ui';
import type { ConsentType } from '@/shared/api';
import { useI18n } from '@/shared/i18n';

interface RevokeDialogProps {
    type: ConsentType;
    busy: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

/** Withdrawing WAREHOUSE_ANALYTICS warns that the project's warehouse records will be deleted (UC6). */
export function RevokeDialog({ type, busy, onConfirm, onCancel }: RevokeDialogProps) {
    const { t } = useI18n();
    return (
        <Dialog
            title={t('settings.revoke.title')}
            onClose={onCancel}
            actions={
                <>
                    <Button onClick={onCancel}>{t('common.cancel')}</Button>
                    <Button variant="danger" onClick={onConfirm} disabled={busy}>
                        {t('common.confirm')}
                    </Button>
                </>
            }
        >
            <p>{t(`settings.revoke.${type}`)}</p>
        </Dialog>
    );
}
