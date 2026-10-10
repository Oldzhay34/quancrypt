package com.quancrypt.core.integration.support;

import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.port.outbound.AuditLogWriter;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Test decorator of the JDBC audit writer: once armed, the next append fails. The audit entry is the last write of
 * every write use case, so a failure there proves that the state change, the outbox event and the idempotency record
 * of the same transaction are rolled back (acid-3nf-database section 7, atomicity).
 */
public final class ArmedAuditLogWriter implements AuditLogWriter {

    private final AuditLogWriter delegate;
    private final AtomicBoolean armed = new AtomicBoolean();

    public ArmedAuditLogWriter(AuditLogWriter delegate) {
        this.delegate = delegate;
    }

    public void failNextAppend() {
        armed.set(true);
    }

    public void disarm() {
        armed.set(false);
    }

    @Override
    public void append(AuditEntry entry) {
        if (armed.getAndSet(false)) {
            throw new IllegalStateException("injected audit failure");
        }
        delegate.append(entry);
    }
}
