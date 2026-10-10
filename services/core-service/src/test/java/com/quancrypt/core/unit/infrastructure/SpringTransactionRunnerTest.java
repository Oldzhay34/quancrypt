package com.quancrypt.core.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.infrastructure.transaction.SpringTransactionRunner;
import com.quancrypt.core.port.outbound.IsolationLevel;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.SimpleTransactionStatus;

/** Retry counts of SpringTransactionRunner per isolation level (D-157), with a transaction manager that only records. */
class SpringTransactionRunnerTest {

    /** Records the isolation of each transaction and whether it committed or rolled back. */
    private static final class RecordingManager implements PlatformTransactionManager {
        final List<Integer> isolations = new ArrayList<>();
        int commits;
        int rollbacks;

        @Override
        public TransactionStatus getTransaction(TransactionDefinition definition) {
            isolations.add(definition == null ? TransactionDefinition.ISOLATION_DEFAULT : definition.getIsolationLevel());
            return new SimpleTransactionStatus();
        }

        @Override
        public void commit(TransactionStatus status) {
            commits++;
        }

        @Override
        public void rollback(TransactionStatus status) {
            rollbacks++;
        }
    }

    private final RecordingManager manager = new RecordingManager();
    private final List<String> retried = new ArrayList<>();
    private final SpringTransactionRunner runner = new SpringTransactionRunner(manager, (isolation, state, attempt) -> retried.add(state));

    private static RuntimeException failure(String sqlState) {
        return new IllegalStateException("wrapped", new SQLException("db", sqlState));
    }

    private int attemptsUntilGivingUp(IsolationLevel level, String sqlState) {
        AtomicInteger attempts = new AtomicInteger();
        assertThatThrownBy(() -> runner.inTransaction(level, () -> {
            attempts.incrementAndGet();
            throw failure(sqlState);
        })).hasRootCauseInstanceOf(SQLException.class);
        return attempts.get();
    }

    @Test
    void serializableRetriesThreeTimesOthersOnce() {
        assertThat(attemptsUntilGivingUp(IsolationLevel.SERIALIZABLE, "40001")).isEqualTo(4);
        assertThat(attemptsUntilGivingUp(IsolationLevel.READ_COMMITTED, "40P01")).isEqualTo(2);
        assertThat(attemptsUntilGivingUp(IsolationLevel.REPEATABLE_READ, "40001")).isEqualTo(2);
        assertThat(retried).containsExactly("40001", "40001", "40001", "40P01", "40001");
    }

    @Test
    void otherFailuresAreNotRetried() {
        assertThat(attemptsUntilGivingUp(IsolationLevel.SERIALIZABLE, "23505")).isEqualTo(1);
        assertThat(retried).isEmpty();
        assertThat(manager.rollbacks).isEqualTo(1);
    }

    @Test
    void aRetriedWorkThatSucceedsCommitsOnceWithTheRequestedIsolation() {
        AtomicInteger attempts = new AtomicInteger();
        String result = runner.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            if (attempts.incrementAndGet() == 1) {
                throw failure("40P01");
            }
            return "done";
        });

        assertThat(result).isEqualTo("done");
        assertThat(manager.commits).isEqualTo(1);
        assertThat(manager.rollbacks).isEqualTo(1);
        assertThat(manager.isolations).containsOnly(TransactionDefinition.ISOLATION_READ_COMMITTED);
    }
}
