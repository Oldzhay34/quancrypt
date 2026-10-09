package com.quancrypt.core.fake;

import com.quancrypt.core.domain.event.DomainEvent;
import com.quancrypt.core.port.outbound.EventAnonymizer;
import java.util.Map;

/** Returns the payload unchanged; the events carry coded fields only. */
public final class PassThroughAnonymizer implements EventAnonymizer {

    @Override
    public Map<String, Object> anonymize(DomainEvent event) {
        return event.payload();
    }
}
