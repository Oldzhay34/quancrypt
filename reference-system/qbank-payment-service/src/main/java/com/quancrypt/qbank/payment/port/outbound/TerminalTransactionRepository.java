package com.quancrypt.qbank.payment.port.outbound;

import com.quancrypt.qbank.payment.domain.model.TerminalTransaction;
import java.util.Optional;
import java.util.UUID;

/** Stores transactions reported by terminals. */
public interface TerminalTransactionRepository {

    /**
     * Stores the transaction unless one with the same transaction id exists.
     *
     * @return true when stored, false when the transaction id was already present (the first record is kept)
     */
    boolean saveIfAbsent(TerminalTransaction transaction);

    Optional<TerminalTransaction> findById(UUID transactionId);
}
