package com.quancrypt.analyzer.infrastructure.time;

import com.quancrypt.analyzer.port.outbound.Clock;
import java.time.Instant;

/** The system UTC clock. */
public final class SystemClock implements Clock {

    private final java.time.Clock clock;

    public SystemClock(java.time.Clock clock) {
        this.clock = clock;
    }

    @Override
    public Instant now() {
        return clock.instant();
    }
}
