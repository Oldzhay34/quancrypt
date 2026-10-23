import type { Evidence } from '@/shared/api/types';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import { referenceLabel, safeHttpsUrl } from '../text';
import styles from './Chat.module.css';

const KIND_KEYS = {
    code_location: 'chat.evidence.code_location',
    tool_call: 'chat.evidence.tool_call',
    knowledge_base: 'chat.evidence.knowledge_base',
} as const satisfies Record<Evidence['kind'], MessageKey>;

function Chip({ item }: { item: Evidence }) {
    const { t } = useI18n();
    const kind = <span className={styles.chipKind}>{t(KIND_KEYS[item.kind])}</span>;
    if (item.kind !== 'knowledge_base') {
        return (
            <>
                {kind}
                <code className={styles.chipCode} title={item.reference}>
                    {referenceLabel(item.reference)}
                </code>
            </>
        );
    }
    const href = safeHttpsUrl(item.reference);
    const label = item.title ?? referenceLabel(item.reference);
    return (
        <>
            {kind}
            {href === null ? (
                <span title={item.reference}>{label}</span>
            ) : (
                <a href={href} target="_blank" rel="noopener noreferrer" title={href}>
                    {label}
                </a>
            )}
            {item.source_version ? (
                <span className={styles.chipVersion}>
                    {t('chat.evidence.version', { version: item.source_version })}
                </span>
            ) : null}
        </>
    );
}

/** Evidence chips: `file:line` and tool-call ids are plain text; a knowledge-base source is a link only when it is an `https:` address. */
export function EvidenceChips({ evidence }: { evidence: Evidence[] }) {
    const { t } = useI18n();
    return (
        <div className={styles.evidence}>
            <h4 className={styles.evidenceLabel}>{t('chat.evidence.label')}</h4>
            <ul className={styles.chips}>
                {evidence.map((item) => (
                    <li key={`${item.kind}:${item.reference}`} className={styles.chip}>
                        <Chip item={item} />
                    </li>
                ))}
            </ul>
        </div>
    );
}
