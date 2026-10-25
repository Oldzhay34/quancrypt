import { useId } from 'react';
import { useI18n } from '@/shared/i18n';
import type { MessageKey } from '@/shared/i18n';
import styles from '../Inventory.module.css';
import { ALGORITHM_FAMILIES, LOCATION_KINDS, PRIORITIES, USAGE_CONTEXTS } from '../filters';
import type { FindingFilter, TestMode } from '../filters';

const TEST_OPTIONS: { value: TestMode; label: MessageKey }[] = [
    { value: 'include', label: 'inventory.tests.include' },
    { value: 'only', label: 'inventory.tests.only' },
    { value: 'exclude', label: 'inventory.tests.exclude' },
];

function Select<T extends string>({
    label,
    value,
    options,
    anyLabel,
    disabled = false,
    onChange,
}: {
    label: string;
    value: T | '';
    options: readonly T[];
    anyLabel: string;
    disabled?: boolean;
    onChange: (value: T | '') => void;
}) {
    const id = useId();
    return (
        <div className={styles.filter}>
            <label htmlFor={id}>{label}</label>
            <select
                id={id}
                value={value}
                disabled={disabled}
                onChange={(event) => onChange(event.target.value as T | '')}
            >
                <option value="">{anyLabel}</option>
                {options.map((option) => (
                    <option key={option} value={option}>
                        {option}
                    </option>
                ))}
            </select>
        </div>
    );
}

/** The five filters of the inventory: algorithm family, priority, usage context, location kind and test code. */
export function FindingFilters({
    filter,
    onChange,
}: {
    filter: FindingFilter;
    onChange: (next: FindingFilter) => void;
}) {
    const { t } = useI18n();
    const testId = useId();
    const any = t('inventory.filter.any');
    return (
        <>
            <Select
                label={t('inventory.col.algorithm')}
                value={filter.algorithmFamily}
                options={ALGORITHM_FAMILIES}
                anyLabel={any}
                onChange={(algorithmFamily) => onChange({ ...filter, algorithmFamily })}
            />
            <Select
                label={t('inventory.col.priority')}
                value={filter.priority}
                options={PRIORITIES}
                anyLabel={any}
                onChange={(priority) => onChange({ ...filter, priority })}
            />
            <Select
                label={t('inventory.col.usage')}
                value={filter.usageContext}
                options={USAGE_CONTEXTS}
                anyLabel={any}
                onChange={(usageContext) => onChange({ ...filter, usageContext })}
            />
            <Select
                label={t('inventory.col.kind')}
                value={filter.tests === 'only' ? 'TEST_CODE' : filter.locationKind}
                options={LOCATION_KINDS}
                anyLabel={any}
                disabled={filter.tests === 'only'}
                onChange={(locationKind) => onChange({ ...filter, locationKind })}
            />
            <div className={styles.filter}>
                <label htmlFor={testId}>{t('inventory.tests')}</label>
                <select
                    id={testId}
                    value={filter.tests}
                    onChange={(event) => onChange({ ...filter, tests: event.target.value as TestMode })}
                >
                    {TEST_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                            {t(option.label)}
                        </option>
                    ))}
                </select>
            </div>
        </>
    );
}
