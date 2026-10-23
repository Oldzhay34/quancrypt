import { Fragment } from 'react';
import type { Evidence } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import { isRefusalText } from '../refusal';
import { hasUnverified, splitUnverified } from '../text';
import { EvidenceChips } from './EvidenceChips';
import { RefusalCard } from './RefusalCard';
import styles from './Chat.module.css';

export type Author = 'user' | 'assistant' | 'scan';

interface MessageBubbleProps {
    author: Author;
    text: string;
    evidence?: Evidence[];
    /** The text is the service's refusal (a `refusal` event). A stored refusal is recognised by its fixed sentence. */
    refusal?: boolean;
}

/** One message. The text is shown as plain text (never HTML or markdown); "[doğrulanamadı]" marks stand out. */
export function MessageBubble({ author, text, evidence = [], refusal = false }: MessageBubbleProps) {
    const { t } = useI18n();
    const label =
        author === 'user'
            ? t('chat.role.user')
            : author === 'scan'
              ? t('chat.role.scan')
              : t('chat.role.assistant');
    const asRefusal = refusal || (author === 'assistant' && isRefusalText(text));
    return (
        <article className={`${styles.bubble} ${styles[author]}`}>
            <h3 className={styles.author}>{label}</h3>
            {asRefusal ? (
                <RefusalCard message={text} />
            ) : (
                <>
                    <p className={styles.text}>
                        {splitUnverified(text).map((part, index) =>
                            part.unverified ? (
                                <mark key={index} className={styles.unverified}>
                                    {part.text}
                                </mark>
                            ) : (
                                <Fragment key={index}>{part.text}</Fragment>
                            ),
                        )}
                    </p>
                    {hasUnverified(text) ? (
                        <p className={styles.unverifiedNote}>{t('chat.unverified.note')}</p>
                    ) : null}
                </>
            )}
            {evidence.length > 0 ? <EvidenceChips evidence={evidence} /> : null}
        </article>
    );
}
