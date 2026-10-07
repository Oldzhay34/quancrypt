package com.quancrypt.qbank.account.support;

import com.quancrypt.qbank.account.port.outbound.Clock;
import java.time.Instant;

/** Test double: always the same instant. */
public final class FixedClock implements Clock {

    private final Instant instant;

    public FixedClock(Instant instant) {
        this.instant = instant;
    }

    @Override
    public Instant now() {
        return instant;
    }
}
