package com.quancrypt.core.port.outbound;

import java.util.UUID;

/** Generates identifiers. */
public interface IdGenerator {

    UUID next();
}
