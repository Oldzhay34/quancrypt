package com.quancrypt.analyzer.fake;

import com.quancrypt.analyzer.port.outbound.Clock;
import java.time.Duration;
import java.time.Instant;

/** Test clock that moves forward by a fixed step on every reading. */
public final class SteppingClock implements Clock {

    private Instant next;
    private final Duration step;

    public SteppingClock(Instant start, Duration step) {
        this.next = start;
        this.step = step;
    }

    @Override
    public Instant now() {
        Instant current = next;
        next = next.plus(step);
        return current;
    }
}
