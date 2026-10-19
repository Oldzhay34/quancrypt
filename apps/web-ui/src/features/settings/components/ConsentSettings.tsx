import { Switch } from '@/shared/ui';
import type { ConsentType } from '@/shared/api';
import { useI18n } from '@/shared/i18n';

export interface ConsentRow {
    type: ConsentType;
    active: boolean;
}

interface ConsentSettingsProps {
    rows: ConsentRow[];
    busy: boolean;
    onEnable: (type: ConsentType) => void;
    onDisable: (type: ConsentType) => void;
}

/** One switch per consent; the container decides what turning a switch on or off does. */
export function ConsentSettings({ rows, busy, onEnable, onDisable }: ConsentSettingsProps) {
    const { t } = useI18n();
    return (
        <div>
            {rows.map(({ type, active }) => (
                <Switch
                    key={type}
                    id={`setting-${type}`}
                    checked={active}
                    disabled={busy}
                    onChange={(value) => (value ? onEnable(type) : onDisable(type))}
                    label={t(`consent.${type}.title`)}
                    description={t(`consent.${type}.desc`)}
                    stateLabel={t(active ? 'consent.state.on' : 'consent.state.off')}
                />
            ))}
        </div>
    );
}
