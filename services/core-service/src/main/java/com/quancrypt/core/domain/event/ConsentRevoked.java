package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.EventType;
import java.util.Map;

/** A consent was revoked or the project was deleted; always written, whatever the consent state (D-21, D-127). */
public record ConsentRevoked(ConsentType consentType, boolean deleteRequested) implements DomainEvent {

    @Override
    public EventType type() {
        return EventType.CONSENT_REVOKED;
    }

    @Override
    public Map<String, Object> payload() {
        return Payloads.of("consent_type", consentType.name(), "delete_requested", deleteRequested);
    }
}
