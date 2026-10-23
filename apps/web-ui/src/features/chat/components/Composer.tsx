import { useId, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { useI18n } from '@/shared/i18n';
import { Button } from '@/shared/ui';
import { MAX_MESSAGE_CHARS } from '../limits';
import styles from './Chat.module.css';

interface ComposerProps {
    /** A turn is running: typing stays possible, sending waits. */
    busy: boolean;
    onSend: (text: string) => void;
}

/** The message box: Enter sends, Shift+Enter adds a line, and Enter during IME composition is left to the IME. */
export function Composer({ busy, onSend }: ComposerProps) {
    const { t } = useI18n();
    const [value, setValue] = useState('');
    const fieldId = useId();
    const hintId = useId();

    const submit = () => {
        const text = value.trim();
        if (text === '' || busy) return;
        onSend(text);
        setValue('');
    };
    const onSubmit = (event: FormEvent) => {
        event.preventDefault();
        submit();
    };
    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
        event.preventDefault();
        submit();
    };

    return (
        <form className={styles.composer} onSubmit={onSubmit}>
            <label htmlFor={fieldId}>{t('chat.composer.label')}</label>
            <textarea
                id={fieldId}
                rows={3}
                value={value}
                maxLength={MAX_MESSAGE_CHARS}
                aria-describedby={hintId}
                onChange={(event) => setValue(event.target.value)}
                onKeyDown={onKeyDown}
            />
            <p id={hintId} className={styles.hint}>
                {t('chat.composer.hint')}
            </p>
            <div className={styles.composerActions}>
                <Button type="submit" variant="primary" disabled={busy || value.trim() === ''}>
                    {t('chat.composer.send')}
                </Button>
            </div>
        </form>
    );
}
