package com.quancrypt.core.port.outbound;

/** Transaction isolation levels a use case may ask for; every plan in core_db_transactions uses READ COMMITTED. */
public enum IsolationLevel {
    READ_COMMITTED,
    REPEATABLE_READ,
    SERIALIZABLE
}
