package com.quancrypt.core.unit.domain;

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
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.model.UsageContext;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class EventPayloadTest {

    private static Set<String> keys(DomainEvent event) {
        return event.payload().keySet();
    }

    @Test
    void everyEventCarriesExactlyTheFieldsOfItsSchema() {
        assertThat(keys(new FindingDetected(AlgorithmFamily.RSA, UsageContext.SIGNATURE, LocationKind.CODE, Priority.P0, Optional.of(1024), 0.9, ClassifiedBy.STATIC)))
                .containsExactlyInAnyOrder("algorithm_family", "usage_context", "location_kind", "priority", "key_size_bits", "confidence", "classified_by");
        assertThat(keys(new TopologyRecorded(2, 1, List.of(new TopologyRecorded.LinkSummary(Protocol.HTTP, true, false)))))
                .containsExactlyInAnyOrder("node_count", "link_count", "links");
        assertThat(keys(new ScanCompleted(3, Map.of(Priority.P0, 1), Optional.of("25"), Optional.empty(), 12)))
                .containsExactlyInAnyOrder("finding_count", "priority_counts", "java_version", "spring_boot_version", "duration_seconds");
        assertThat(keys(new PlanCreated(2, Map.of(StrategyCode.FIX_WEAK_CLASSIC, 2), Map.of(Effort.S, 2))))
                .containsExactlyInAnyOrder("item_count", "strategy_counts", "effort_counts");
        assertThat(keys(new PlanItemTransitioned(StrategyCode.HYBRID_TLS_KEX, Effort.M, PlanItemStateCode.PLANNED, PlanItemStateCode.APPROVED)))
                .containsExactlyInAnyOrder("strategy", "effort", "from_state", "to_state");
        assertThat(keys(new ProjectRuntimeChanged(Optional.empty(), new ProjectRuntimeChanged.Snapshot("25", Optional.of("4.1.1")))))
                .containsExactlyInAnyOrder("previous", "current");
        assertThat(keys(new ConsentRevoked(ConsentType.WAREHOUSE_ANALYTICS, true))).containsExactlyInAnyOrder("consent_type", "delete_requested");
    }

    @Test
    void payloadsCarryCodesAndNumbersNeverPathsOrSymbols() {
        FindingDetected event = new FindingDetected(AlgorithmFamily.RSA, UsageContext.SIGNATURE, LocationKind.CODE, Priority.P0, Optional.empty(), 0.9, ClassifiedBy.LLM);
        assertThat(event.payload()).containsEntry("algorithm_family", "RSA").containsEntry("priority", "P0").containsEntry("key_size_bits", null);
        assertThat(event.type()).isEqualTo(EventType.FINDING_DETECTED);
        ScanCompleted completed = new ScanCompleted(3, Map.of(Priority.P1, 2, Priority.P0, 1), Optional.of("25"), Optional.of("4.1.1"), 7);
        assertThat(completed.payload().get("priority_counts")).isEqualTo(Map.of("P0", 1, "P1", 2));
        ProjectRuntimeChanged changed = new ProjectRuntimeChanged(
                Optional.of(new ProjectRuntimeChanged.Snapshot("21", Optional.empty())), new ProjectRuntimeChanged.Snapshot("25", Optional.empty()));
        assertThat(changed.payload().get("previous")).isInstanceOf(Map.class);
        assertThat(((Map<?, ?>) changed.payload().get("previous")).get("java_version")).isEqualTo("21");
        assertThat(((Map<?, ?>) changed.payload().get("current")).get("java_version")).isEqualTo("25");
        assertThat(DomainEvent.SCHEMA_VERSION).isEqualTo(1);
    }

    @Test
    void topologyEventListsOnlyCodedFactsOfEachLink() {
        TopologyRecorded event = new TopologyRecorded(2, 1, List.of(new TopologyRecorded.LinkSummary(Protocol.MQTT, true, true)));
        assertThat(event.type()).isEqualTo(EventType.TOPOLOGY_RECORDED);
        Object links = event.payload().get("links");
        assertThat(links).isInstanceOf(List.class);
        assertThat(((List<?>) links).get(0)).isEqualTo(Map.of("protocol", "MQTT", "tls", true, "mtls", true));
    }
}
