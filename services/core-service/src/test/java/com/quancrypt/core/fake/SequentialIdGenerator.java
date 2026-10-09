package com.quancrypt.core.fake;

import com.quancrypt.core.port.outbound.IdGenerator;
import java.util.UUID;

/** Deterministic identifiers 00000000-0000-0000-0000-000000000001, ...002, and so on. */
public final class SequentialIdGenerator implements IdGenerator {

    private long next = 1;

    @Override
    public UUID next() {
        return new UUID(0, next++);
    }
}
