package com.quancrypt.qbank.payment.infrastructure.persistence;

import com.quancrypt.qbank.payment.domain.model.TerminalTransaction;
import com.quancrypt.qbank.payment.port.outbound.TerminalTransactionRepository;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Holds terminal transactions in memory; they are lost when the service stops. */
public final class InMemoryTerminalTransactionRepository implements TerminalTransactionRepository {

    private final Map<UUID, TerminalTransaction> transactions = new ConcurrentHashMap<>();

    @Override
    public boolean saveIfAbsent(TerminalTransaction transaction) {
        return transactions.putIfAbsent(transaction.transactionId(), transaction) == null;
    }

    @Override
    public Optional<TerminalTransaction> findById(UUID transactionId) {
        return Optional.ofNullable(transactions.get(transactionId));
    }
}
