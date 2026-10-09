package com.quancrypt.core.fake;

import com.quancrypt.core.port.outbound.Clock;
import java.time.Duration;
import java.time.Instant;

/** A clock tests set and move by hand. */
public final class FixedClock implements Clock {

    private Instant now;

    public FixedClock(Instant start) {
        this.now = start;
    }

    @Override
    public Instant now() {
        return now;
    }

    public void advance(Duration by) {
        now = now.plus(by);
    }
}
