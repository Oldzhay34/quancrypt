package com.quancrypt.core.port.outbound;

import java.time.Instant;

/** The current time; a port so tests are deterministic. */
public interface Clock {

    Instant now();
}
