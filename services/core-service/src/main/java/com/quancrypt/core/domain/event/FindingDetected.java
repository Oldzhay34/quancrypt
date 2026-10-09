package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.UsageContext;
import java.util.Map;
import java.util.Optional;

/** A scan recorded a new crypto finding (RecordFindings). */
public record FindingDetected(
        AlgorithmFamily algorithmFamily,
        UsageContext usageContext,
        LocationKind locationKind,
        Priority priority,
        Optional<Integer> keySizeBits,
        double confidence,
        ClassifiedBy classifiedBy) implements DomainEvent {

    @Override
    public EventType type() {
        return EventType.FINDING_DETECTED;
    }

    @Override
    public Map<String, Object> payload() {
        return Payloads.of(
                "algorithm_family", algorithmFamily.name(),
                "usage_context", usageContext.name(),
                "location_kind", locationKind.name(),
                "priority", priority.name(),
                "key_size_bits", Payloads.orNull(keySizeBits),
                "confidence", confidence,
                "classified_by", classifiedBy.name());
    }
}
