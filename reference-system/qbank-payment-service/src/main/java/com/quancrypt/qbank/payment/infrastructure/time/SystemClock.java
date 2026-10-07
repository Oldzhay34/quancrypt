package com.quancrypt.qbank.payment.infrastructure.time;

import com.quancrypt.qbank.payment.port.outbound.Clock;
import java.time.Instant;

/** The system's UTC clock. */
public class SystemClock implements Clock {

    @Override
    public Instant now() {
        return Instant.now();
    }
}
