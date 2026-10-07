package com.quancrypt.qbank.account.infrastructure.time;

import com.quancrypt.qbank.account.port.outbound.Clock;
import java.time.Instant;

/** The system's UTC clock. */
public class SystemClock implements Clock {

    @Override
    public Instant now() {
        return Instant.now();
    }
}
