package com.quancrypt.core.infrastructure.time;

import com.quancrypt.core.port.outbound.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

/** The system UTC clock, truncated to microseconds so a value survives a timestamptz round trip unchanged. */
public final class SystemClock implements Clock {

    private final java.time.Clock clock;

    public SystemClock(java.time.Clock clock) {
        this.clock = clock;
    }

    @Override
    public Instant now() {
        return clock.instant().truncatedTo(ChronoUnit.MICROS);
    }
}
