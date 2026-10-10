package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.TransactionRunnerContract;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.fake.FakeTransactionRunner;
import com.quancrypt.core.fake.InMemoryDatabase;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** The snapshot-restoring fake runner against the TransactionRunner contract. */
class FakeTransactionRunnerContractTest extends TransactionRunnerContract {

    @Override
    protected Subject newSubject() {
        InMemoryDatabase db = new InMemoryDatabase();
        FakeTransactionRunner runner = new FakeTransactionRunner(db);
        return new Subject() {
            @Override
            public TransactionRunner runner() {
                return runner;
            }

            @Override
            public void write() {
                db.audit.add(new AuditEntry(UUID.randomUUID(), Instant.parse("2026-10-09T10:00:00Z"), AuditAction.OUTBOX_EVENTS_RELAYED,
                        Optional.empty(), Optional.empty(), CallerKind.INTERNAL));
            }

            @Override
            public int written() {
                return db.audit.size();
            }
        };
    }
}
