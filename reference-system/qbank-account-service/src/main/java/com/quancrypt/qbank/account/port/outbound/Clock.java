package com.quancrypt.qbank.account.port.outbound;

import java.time.Instant;

/** Source of the current time. */
public interface Clock {

    Instant now();
}
