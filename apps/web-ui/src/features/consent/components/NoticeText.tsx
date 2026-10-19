import styles from './NoticeText.module.css';

/** The notice is plain text from the server: it is rendered as text (never as HTML) and keeps its line breaks. */
export function NoticeText({ text }: { text: string }) {
    return <div className={styles.notice}>{text}</div>;
}
