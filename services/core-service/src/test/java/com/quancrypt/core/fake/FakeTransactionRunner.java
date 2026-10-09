package com.quancrypt.core.fake;

import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

/** Runs work against the in-memory database and restores a snapshot when it fails, like a rollback. */
public final class FakeTransactionRunner implements TransactionRunner {

    private final InMemoryDatabase db;
    private final List<IsolationLevel> isolations = new ArrayList<>();

    public FakeTransactionRunner(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public <T> T inTransaction(IsolationLevel isolation, Supplier<T> work) {
        isolations.add(isolation);
        InMemoryDatabase.Snapshot snapshot = db.snapshot();
        try {
            return work.get();
        } catch (RuntimeException e) {
            db.restore(snapshot);
            throw e;
        }
    }

    public List<IsolationLevel> isolations() {
        return List.copyOf(isolations);
    }
}
