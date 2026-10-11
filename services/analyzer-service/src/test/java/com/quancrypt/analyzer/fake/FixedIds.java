package com.quancrypt.analyzer.fake;

import com.quancrypt.analyzer.port.outbound.IdGenerator;
import java.util.UUID;

/** Test id generator that always returns the same id. */
public final class FixedIds implements IdGenerator {

    public static final UUID ID = UUID.fromString("00000000-0000-4000-8000-000000000001");

    @Override
    public UUID newId() {
        return ID;
    }
}
