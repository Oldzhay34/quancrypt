import styles from './Switch.module.css';

interface SwitchProps {
    id: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
    label: string;
    description?: string;
    stateLabel: string;
    disabled?: boolean;
}

export function Switch({ id, checked, onChange, label, description, stateLabel, disabled }: SwitchProps) {
    return (
        <div className={styles.row}>
            <div className={styles.text}>
                <label htmlFor={id} className={styles.label}>
                    {label}
                </label>
                {description ? <p className={styles.description}>{description}</p> : null}
            </div>
            <div className={styles.control}>
                <input
                    id={id}
                    type="checkbox"
                    role="switch"
                    className={styles.input}
                    checked={checked}
                    disabled={disabled}
                    onChange={(event) => onChange(event.target.checked)}
                />
                <span aria-hidden="true" className={styles.state}>
                    {stateLabel}
                </span>
            </div>
        </div>
    );
}
