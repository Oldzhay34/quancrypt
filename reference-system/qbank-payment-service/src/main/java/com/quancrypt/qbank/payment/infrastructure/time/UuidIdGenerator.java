package com.quancrypt.qbank.payment.infrastructure.time;

import com.quancrypt.qbank.payment.port.outbound.IdGenerator;
import java.util.UUID;

/** Random version 4 UUIDs. */
public final class UuidIdGenerator implements IdGenerator {

    @Override
    public UUID newId() {
        return UUID.randomUUID();
    }
}
