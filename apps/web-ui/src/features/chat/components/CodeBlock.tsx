import { Check, Copy, Download } from 'lucide-react';
import { useState } from 'react';
import type { Snippet } from '@/shared/api/types';
import { saveFile } from '@/shared/download';
import { useI18n } from '@/shared/i18n';
import { highlight, languageOf } from '../highlight';
import styles from './CodeBlock.module.css';

/** Source lines as a dark code box with the language, download and copy (D-361c); the finding's line is marked. */
export function CodeBlock({ snippet, line }: { snippet: Snippet; line: number }) {
    const { t } = useI18n();
    const [copied, setCopied] = useState(false);
    const language = languageOf(snippet.path);
    const text = snippet.lines.map((item) => item.text).join('\n');
    const filename = snippet.path.slice(snippet.path.lastIndexOf('/') + 1);

    const copy = () => {
        // Without clipboard access (an insecure origin, a refused permission) the button simply does nothing.
        void navigator.clipboard
            ?.writeText(text)
            .then(() => setCopied(true))
            .catch(() => undefined);
    };

    return (
        <div className={styles.box}>
            <div className={styles.head}>
                <span className={styles.language}>{language}</span>
                <span className={styles.actions}>
                    <button
                        type="button"
                        className={styles.action}
                        aria-label={t('code.download')}
                        title={t('code.download')}
                        onClick={() => saveFile(new Blob([text], { type: 'text/plain' }), filename)}
                    >
                        <Download aria-hidden="true" className="h-4 w-4" />
                    </button>
                    <button
                        type="button"
                        className={styles.action}
                        aria-label={copied ? t('code.copied') : t('code.copy')}
                        title={copied ? t('code.copied') : t('code.copy')}
                        onClick={copy}
                    >
                        {copied ? (
                            <Check aria-hidden="true" className="h-4 w-4" />
                        ) : (
                            <Copy aria-hidden="true" className="h-4 w-4" />
                        )}
                    </button>
                </span>
            </div>
            <pre className={styles.pre} tabIndex={0} aria-label={snippet.path}>
                <code>
                    {snippet.lines.map((item) => (
                        <span
                            key={item.number}
                            className={item.number === line ? `${styles.line} ${styles.marked}` : styles.line}
                        >
                            <span className={styles.number}>{item.number}</span>
                            {highlight(item.text, language).map((token, index) => (
                                <span
                                    key={index}
                                    className={styles[token.kind === 'number' ? 'literal' : token.kind]}
                                >
                                    {token.text}
                                </span>
                            ))}
                            {'\n'}
                        </span>
                    ))}
                </code>
            </pre>
        </div>
    );
}
