package com.quancrypt.core.infrastructure.transaction;

import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.EnumMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Runs use case work in one transaction with TransactionTemplate. On a serialization failure (40001) or a deadlock
 * (40P01) the whole transaction is retried: at most 3 times under SERIALIZABLE, at most once under the other levels
 * (D-157, D-143). Any other failure rolls back and is rethrown unchanged.
 */
public final class SpringTransactionRunner implements TransactionRunner {

    static final int SERIALIZABLE_RETRIES = 3;
    static final int DEFAULT_RETRIES = 1;
    private static final Set<String> RETRYABLE = Set.of(SqlErrors.SERIALIZATION_FAILURE, SqlErrors.DEADLOCK_DETECTED);

    /** Told about every retry with the SQLSTATE that caused it; the service logs it. */
    @FunctionalInterface
    public interface RetryListener {
        void retrying(IsolationLevel isolation, String sqlState, int attempt);
    }

    private final Map<IsolationLevel, TransactionTemplate> templates = new EnumMap<>(IsolationLevel.class);
    private final RetryListener listener;

    public SpringTransactionRunner(PlatformTransactionManager transactionManager, RetryListener listener) {
        this.listener = listener;
        templates.put(IsolationLevel.READ_COMMITTED, template(transactionManager, TransactionDefinition.ISOLATION_READ_COMMITTED));
        templates.put(IsolationLevel.REPEATABLE_READ, template(transactionManager, TransactionDefinition.ISOLATION_REPEATABLE_READ));
        templates.put(IsolationLevel.SERIALIZABLE, template(transactionManager, TransactionDefinition.ISOLATION_SERIALIZABLE));
    }

    private static TransactionTemplate template(PlatformTransactionManager manager, int isolation) {
        TransactionTemplate template = new TransactionTemplate(manager);
        template.setIsolationLevel(isolation);
        return template;
    }

    @Override
    public <T> T inTransaction(IsolationLevel isolation, Supplier<T> work) {
        TransactionTemplate template = templates.get(isolation);
        int retriesLeft = maxRetries(isolation);
        while (true) {
            try {
                return template.execute(status -> work.get());
            } catch (RuntimeException e) {
                if (retriesLeft == 0 || !isRetryable(e)) {
                    throw e;
                }
                retriesLeft--;
                listener.retrying(isolation, SqlErrors.sqlState(e).orElseThrow(), maxRetries(isolation) - retriesLeft);
            }
        }
    }

    static int maxRetries(IsolationLevel isolation) {
        return isolation == IsolationLevel.SERIALIZABLE ? SERIALIZABLE_RETRIES : DEFAULT_RETRIES;
    }

    static boolean isRetryable(Throwable failure) {
        return SqlErrors.sqlState(failure).filter(RETRYABLE::contains).isPresent();
    }
}
