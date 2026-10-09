package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.EventType;
import java.util.Map;

/** A domain event; the payload holds coded fields and numbers only, no paths, symbols or free text (D-20). */
public sealed interface DomainEvent
        permits FindingDetected, TopologyRecorded, ScanCompleted, PlanCreated, PlanItemTransitioned, ProjectRuntimeChanged, ConsentRevoked {

    int SCHEMA_VERSION = 1;

    EventType type();

    /** The inner event payload as the event schema defines it (snake_case keys). */
    Map<String, Object> payload();
}
