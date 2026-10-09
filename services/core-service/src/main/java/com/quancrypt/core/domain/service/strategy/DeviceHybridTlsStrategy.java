package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.model.UsageContext;

/** P1: hybrid TLS for field-device links (MQTT over TLS), decided by the device-side OpenSSL (D-148). */
public final class DeviceHybridTlsStrategy extends AbstractMigrationStrategy {

    public DeviceHybridTlsStrategy() {
        super(StrategyCode.DEVICE_HYBRID_TLS);
    }

    @Override
    boolean matches(FindingFacts facts) {
        return facts.priority() == Priority.P1 && facts.usage().usage() == UsageContext.TLS_KEY_EXCHANGE && facts.onDeviceLink();
    }
}
