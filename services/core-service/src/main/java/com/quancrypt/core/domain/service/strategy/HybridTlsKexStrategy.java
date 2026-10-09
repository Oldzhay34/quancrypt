package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.model.UsageContext;
import java.util.ArrayList;
import java.util.List;

/** P1: hybrid key exchange for service-to-service TLS; the JDK 27 default and Bouncy Castle are noted, not required (D-150). */
public final class HybridTlsKexStrategy extends AbstractMigrationStrategy {

    private static final int JDK_WITH_HYBRID_DEFAULT = 27;

    public HybridTlsKexStrategy() {
        super(StrategyCode.HYBRID_TLS_KEX);
    }

    @Override
    boolean matches(FindingFacts facts) {
        return facts.priority() == Priority.P1 && facts.usage().usage() == UsageContext.TLS_KEY_EXCHANGE && !facts.onDeviceLink();
    }

    @Override
    public StrategyPlan plan(FindingFacts facts) {
        List<PlanNote> notes = new ArrayList<>();
        if (facts.javaVersion().filter(v -> v.isAtLeast(JDK_WITH_HYBRID_DEFAULT)).isEmpty()) {
            notes.add(PlanNote.HYBRID_TLS_DEFAULT_ARRIVES_IN_JDK_27);
            notes.add(PlanNote.BOUNCY_CASTLE_ALTERNATIVE);
        }
        return new StrategyPlan(code(), notes);
    }
}
