package com.quancrypt.core.infrastructure.id;

import com.quancrypt.core.port.outbound.IdGenerator;
import java.util.UUID;

/** Random (version 4) UUIDs for every row id. */
public final class RandomIdGenerator implements IdGenerator {

    @Override
    public UUID next() {
        return UUID.randomUUID();
    }
}
