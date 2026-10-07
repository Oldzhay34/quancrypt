package com.quancrypt.qbank.payment.port.outbound;

import java.time.Instant;

/** Source of the current time. */
public interface Clock {

    Instant now();
}
