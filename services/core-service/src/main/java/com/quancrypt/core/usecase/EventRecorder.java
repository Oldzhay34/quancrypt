package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.DomainEvent;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.EventAnonymizer;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.OutboxWriter;

/** Writes domain events to the outbox, anonymized, inside the caller's transaction (D-20). */
public final class EventRecorder {

    private final OutboxWriter outbox;
    private final EventAnonymizer anonymizer;
    private final Clock clock;
    private final IdGenerator ids;

    public EventRecorder(OutboxWriter outbox, EventAnonymizer anonymizer, Clock clock, IdGenerator ids) {
        this.outbox = outbox;
        this.anonymizer = anonymizer;
        this.clock = clock;
        this.ids = ids;
    }

    /** Writes the event only when warehouse consent exists (D-21). */
    void recordIfConsented(boolean warehouseConsent, ProjectKey projectKey, DomainEvent event) {
        if (warehouseConsent) {
            record(projectKey, event);
        }
    }

    /** Writes the event whatever the consent state; only revocation events are written this way (D-21). */
    void record(ProjectKey projectKey, DomainEvent event) {
        outbox.append(new OutboxRecord(
                ids.next(), event.type(), DomainEvent.SCHEMA_VERSION, projectKey, clock.now(), anonymizer.anonymize(event)));
    }
}
