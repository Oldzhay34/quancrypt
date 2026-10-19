import styles from './Spinner.module.css';

export function Spinner({ label }: { label: string }) {
    return (
        <p role="status" className={styles.spinner}>
            {label}
        </p>
    );
}
