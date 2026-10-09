package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.event.DomainEvent;
import java.util.Map;

/** Anonymizes an event before it is written to the outbox (D-20). */
public interface EventAnonymizer {

    /** The payload with anything not coded redacted; the project key is already an HMAC. */
    Map<String, Object> anonymize(DomainEvent event);
}
