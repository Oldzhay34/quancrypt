package com.quancrypt.core.port.outbound;

import java.util.function.Supplier;

/**
 * Runs work in one transaction: commit on return, rollback on any exception.
 * Contract: on a deadlock (40P01) or serialization failure (40001) the work is retried at most 3 times under
 * SERIALIZABLE and at most once under the other levels, then the failure is rethrown (D-143, D-157); the work must
 * therefore be safe to run again.
 */
public interface TransactionRunner {

    <T> T inTransaction(IsolationLevel isolation, Supplier<T> work);

    default void inTransaction(IsolationLevel isolation, Runnable work) {
        inTransaction(isolation, () -> {
            work.run();
            return null;
        });
    }
}
