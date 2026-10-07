package com.quancrypt.qbank.payment.port.outbound;

import java.util.UUID;

/** Source of new identifiers. */
public interface IdGenerator {

    UUID newId();
}
