import { useI18n } from '@/shared/i18n';
import styles from './QuantumComputer.module.css';

/*
 * The drawing the user gave (D-361a): a controller above five cooling stages and the qubits. The labels are the ones in
 * that picture. It draws itself from the top down.
 */
const STAGES = [
    { y: 100, x: 84, width: 255, label: '300 K' },
    { y: 175, x: 102, width: 218, label: '50 K' },
    { y: 250, x: 121, width: 180, label: '4 K' },
    { y: 325, x: 140, width: 142, label: '100 mK' },
    { y: 400, x: 159, width: 105, label: '10 mK' },
];
const RODS = [177, 211, 245];
const PINS = [-14, 0, 14];

export function QuantumComputer() {
    const { t } = useI18n();
    return (
        <svg
            className={styles.drawing}
            viewBox="60 20 340 430"
            role="img"
            aria-label={t('chat.hero.drawing')}
        >
            <g className={`${styles.part} ${styles.s0}`}>
                <rect className={styles.chip} x="192" y="34" width="38" height="38" rx="7" />
                <rect className={styles.core} x="201" y="43" width="20" height="20" rx="2" />
                {PINS.map((offset) => (
                    <path
                        key={offset}
                        className={styles.pin}
                        d={`M${211 + offset} 28v6M${211 + offset} 72v6M186 ${53 + offset}h6M230 ${53 + offset}h6`}
                    />
                ))}
                <text className={styles.label} x="245" y="57">
                    FPGA controller
                </text>
            </g>
            <path className={styles.arrow} d="M125 80V430" pathLength={1} />
            <path className={`${styles.head} ${styles.s6}`} d="M121 428h8l-4 8z" />
            {STAGES.map((stage, index) => (
                <g key={stage.label}>
                    {RODS.map((x) =>
                        index < STAGES.length - 1 ? (
                            <rect
                                key={x}
                                className={`${styles.rod} ${styles[`s${index + 1}`]}`}
                                x={x - 2}
                                y={stage.y + 6}
                                width="4"
                                height="64"
                            />
                        ) : null,
                    )}
                    <rect
                        className={`${styles.plate} ${styles[`s${index + 1}`]}`}
                        x={stage.x}
                        y={stage.y - 6}
                        width={stage.width}
                        height="12"
                        rx="3"
                    />
                    <text
                        className={`${styles.label} ${styles.part} ${styles[`s${index + 1}`]}`}
                        x={stage.x + stage.width + 9}
                        y={stage.y + 4}
                    >
                        {stage.label}
                    </text>
                </g>
            ))}
            <g className={`${styles.part} ${styles.s6}`}>
                <rect className={styles.rod} x="209" y="406" width="4" height="18" />
                <rect className={styles.qubits} x="189" y="423" width="45" height="24" rx="3" />
                <text className={styles.label} x="245" y="439">
                    qubits
                </text>
            </g>
        </svg>
    );
}
