package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.infrastructure.transaction.SpringTransactionRunner;
import com.quancrypt.core.integration.support.PostgresTestDatabase;
import com.quancrypt.core.integration.support.RetryLog;
import com.quancrypt.core.port.outbound.IsolationLevel;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

/**
 * SpringTransactionRunner on PostgreSQL: a real serialization failure (40001) under SERIALIZABLE is retried and the
 * work then succeeds; work runs with the requested isolation level and a failure rolls everything back (D-157).
 */
class TransactionRunnerTest {

    private final PostgresTestDatabase database = PostgresTestDatabase.get();
    private final JdbcClient jdbc = JdbcClient.create(database.app());
    private final RetryLog retries = new RetryLog();
    private final SpringTransactionRunner runner = new SpringTransactionRunner(new DataSourceTransactionManager(database.app()), retries);

    @BeforeEach
    void empty() {
        database.truncate();
    }

    @Test
    void workRunsWithTheRequestedIsolation() {
        for (IsolationLevel level : IsolationLevel.values()) {
            String seen = runner.inTransaction(level, () -> jdbc.sql("SHOW transaction_isolation").query(String.class).single());
            assertThat(seen).isEqualTo(level.name().toLowerCase().replace('_', ' '));
        }
    }

    @Test
    void failureRollsBackEverything() {
        Throwable failure = catchThrowable(() -> runner.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            jdbc.sql("INSERT INTO audit_log (id, occurred_at, action_code, project_key, subject_id, caller_kind) "
                    + "VALUES (gen_random_uuid(), now(), 'OUTBOX_EVENTS_RELAYED', NULL, NULL, 'INTERNAL')").update();
            throw new IllegalStateException("boom");
        }));

        assertThat(failure).hasMessage("boom");
        assertThat(jdbc.sql("SELECT count(*) FROM audit_log").query(Integer.class).single()).isZero();
        assertThat(retries.sqlStates()).isEmpty();
    }

    /**
     * Two SERIALIZABLE transactions each read the audit count and insert a row; read/write dependencies make one of them
     * fail with 40001 at commit, the runner retries it and both finally commit.
     */
    @Test
    void serializationFailureIsRetried() throws Exception {
        CountDownLatch bothRead = new CountDownLatch(2);
        AtomicInteger attempts = new AtomicInteger();
        Runnable work = () -> runner.inTransaction(IsolationLevel.SERIALIZABLE, () -> {
            int attempt = attempts.incrementAndGet();
            jdbc.sql("SELECT count(*) FROM audit_log WHERE caller_kind = 'INTERNAL'").query(Integer.class).single();
            if (attempt <= 2) {
                bothRead.countDown();
                await(bothRead);
            }
            jdbc.sql("INSERT INTO audit_log (id, occurred_at, action_code, project_key, subject_id, caller_kind) "
                    + "VALUES (gen_random_uuid(), now(), 'OUTBOX_EVENTS_RELAYED', NULL, NULL, 'INTERNAL')").update();
            return null;
        });
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> a = pool.submit(work);
            Future<?> b = pool.submit(work);
            a.get(60, TimeUnit.SECONDS);
            b.get(60, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
        }

        assertThat(jdbc.sql("SELECT count(*) FROM audit_log").query(Integer.class).single()).isEqualTo(2);
        assertThat(retries.sqlStates()).containsOnly(SqlErrors.SERIALIZATION_FAILURE).isNotEmpty();
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await(10, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }
}
