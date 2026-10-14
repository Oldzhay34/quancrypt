package com.quancrypt.analyzer.infrastructure.id;

import com.quancrypt.analyzer.port.outbound.IdGenerator;
import java.util.UUID;

/** Random (version 4) UUIDs for analysis ids and CBOM serial numbers. */
public final class RandomIdGenerator implements IdGenerator {

    @Override
    public UUID newId() {
        return UUID.randomUUID();
    }
}
