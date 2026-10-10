package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.TransactionRunnerContract;
import com.quancrypt.core.infrastructure.transaction.SpringTransactionRunner;
import com.quancrypt.core.integration.support.PostgresTestDatabase;
import com.quancrypt.core.integration.support.RetryLog;
import com.quancrypt.core.port.outbound.TransactionRunner;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

/** SpringTransactionRunner on PostgreSQL against the TransactionRunner contract; the guarded store is audit_log. */
class SpringTransactionRunnerContractTest extends TransactionRunnerContract {

    @Override
    protected Subject newSubject() {
        PostgresTestDatabase database = PostgresTestDatabase.get();
        database.truncate();
        JdbcClient jdbc = JdbcClient.create(database.app());
        SpringTransactionRunner runner = new SpringTransactionRunner(new DataSourceTransactionManager(database.app()), new RetryLog());
        return new Subject() {
            @Override
            public TransactionRunner runner() {
                return runner;
            }

            @Override
            public void write() {
                jdbc.sql("""
                        INSERT INTO audit_log (id, occurred_at, action_code, project_key, subject_id, caller_kind)
                        VALUES (gen_random_uuid(), now(), 'OUTBOX_EVENTS_RELAYED', NULL, NULL, 'INTERNAL')""").update();
            }

            @Override
            public int written() {
                return jdbc.sql("SELECT count(*) FROM audit_log").query(Integer.class).single();
            }
        };
    }
}
