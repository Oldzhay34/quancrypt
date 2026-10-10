package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.TransactionRunner;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * TransactionRunner contract shared by the fake and the Spring runner: commit on return, rollback on any exception,
 * which is rethrown unchanged. The retry on 40001/40P01 (D-157) cannot happen in memory, so it is not part of this
 * shared contract; SpringTransactionRunnerTest and TransactionRunnerTest cover it for the real runner.
 */
public abstract class TransactionRunnerContract {

    /** The runner under test plus a store it guards: a write that the transaction may keep or roll back. */
    protected interface Subject {
        TransactionRunner runner();

        void write();

        int written();
    }

    private Subject subject;

    protected abstract Subject newSubject();

    @BeforeEach
    void create() {
        subject = newSubject();
    }

    @Test
    void returningCommitsAndReturnsTheValue() {
        String result = subject.runner().inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            subject.write();
            return "done";
        });

        assertThat(result).isEqualTo("done");
        assertThat(subject.written()).isEqualTo(1);
    }

    @Test
    void theRunnableFormCommitsToo() {
        subject.runner().inTransaction(IsolationLevel.READ_COMMITTED, subject::write);

        assertThat(subject.written()).isEqualTo(1);
    }

    @Test
    void anExceptionRollsBackAndIsRethrownUnchanged() {
        IllegalStateException boom = new IllegalStateException("boom");

        Throwable thrown = catchThrowable(() -> subject.runner().inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            subject.write();
            throw boom;
        }));

        assertThat(thrown).isSameAs(boom);
        assertThat(subject.written()).isZero();
    }
}
