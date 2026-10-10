package com.quancrypt.core.contract;

import com.quancrypt.core.domain.event.ConsentRevoked;
import com.quancrypt.core.domain.event.DomainEvent;
import com.quancrypt.core.domain.event.FindingDetected;
import com.quancrypt.core.domain.event.PlanCreated;
import com.quancrypt.core.domain.event.PlanItemTransitioned;
import com.quancrypt.core.domain.event.ProjectRuntimeChanged;
import com.quancrypt.core.domain.event.ScanCompleted;
import com.quancrypt.core.domain.event.TopologyRecorded;
import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.model.UsageContext;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** One or more instances of every domain event type, including the optional (null) branches of their payloads. */
public final class SampleEvents {

    private SampleEvents() {
    }

    public static List<DomainEvent> all() {
        return List.of(
                new FindingDetected(AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE, LocationKind.CODE, Priority.P1, Optional.of(2048), 0.9,
                        ClassifiedBy.STATIC),
                new FindingDetected(AlgorithmFamily.ECDSA, UsageContext.SIGNATURE, LocationKind.CONFIG, Priority.P2, Optional.empty(), 0.5,
                        ClassifiedBy.LLM),
                new TopologyRecorded(3, 2, List.of(new TopologyRecorded.LinkSummary(Protocol.HTTP, true, true),
                        new TopologyRecorded.LinkSummary(Protocol.MQTT, true, false))),
                new ScanCompleted(3, Map.of(Priority.P0, 1, Priority.P1, 2), Optional.of("21"), Optional.of("4.1.1"), 42),
                new ScanCompleted(0, Map.of(), Optional.empty(), Optional.empty(), 0),
                new PlanCreated(2, Map.of(StrategyCode.HYBRID_TLS_KEX, 1, StrategyCode.FIX_WEAK_CLASSIC, 1), Map.of(Effort.S, 1, Effort.M, 1)),
                new PlanItemTransitioned(StrategyCode.HYBRID_TLS_KEX, Effort.M, PlanItemStateCode.PLANNED, PlanItemStateCode.APPROVED),
                new ProjectRuntimeChanged(Optional.empty(), new ProjectRuntimeChanged.Snapshot("21", Optional.empty())),
                new ProjectRuntimeChanged(Optional.of(new ProjectRuntimeChanged.Snapshot("17", Optional.of("3.2.0"))),
                        new ProjectRuntimeChanged.Snapshot("25", Optional.of("4.1.1"))),
                new ConsentRevoked(ConsentType.WAREHOUSE_ANALYTICS, false),
                new ConsentRevoked(ConsentType.MODEL_TRAINING, true));
    }
}
