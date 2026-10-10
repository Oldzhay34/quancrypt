package com.quancrypt.core.integration.support;

import com.quancrypt.core.infrastructure.transaction.SpringTransactionRunner;
import com.quancrypt.core.port.outbound.IsolationLevel;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/** Records the SQLSTATE of every transaction retry, so a test can prove that no deadlock happened. */
public final class RetryLog implements SpringTransactionRunner.RetryListener {

    private final List<String> sqlStates = new CopyOnWriteArrayList<>();

    @Override
    public void retrying(IsolationLevel isolation, String sqlState, int attempt) {
        sqlStates.add(sqlState);
    }

    public List<String> sqlStates() {
        return List.copyOf(sqlStates);
    }

    public void clear() {
        sqlStates.clear();
    }
}
