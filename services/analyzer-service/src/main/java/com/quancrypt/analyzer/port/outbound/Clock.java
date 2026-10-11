package com.quancrypt.analyzer.port.outbound;

import java.time.Instant;

/** The current time. */
public interface Clock {

    Instant now();
}
