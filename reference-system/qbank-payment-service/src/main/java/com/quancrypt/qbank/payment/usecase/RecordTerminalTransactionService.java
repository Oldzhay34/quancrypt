package com.quancrypt.qbank.payment.usecase;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.TerminalTransaction;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.RecordTerminalTransactionCommand;
import com.quancrypt.qbank.payment.port.inbound.RecordTerminalTransactionUseCase;
import com.quancrypt.qbank.payment.port.outbound.TerminalTransactionRepository;
import java.util.Objects;

/** Records a terminal transaction once; a repeated transaction id is ignored (D-103). */
public final class RecordTerminalTransactionService implements RecordTerminalTransactionUseCase {

    private final TerminalTransactionRepository transactions;

    public RecordTerminalTransactionService(TerminalTransactionRepository transactions) {
        this.transactions = Objects.requireNonNull(transactions, "transactions");
    }

    @Override
    public boolean record(RecordTerminalTransactionCommand command) {
        if (command == null || command.transactionId() == null || command.terminalId() == null
                || command.accountId() == null || command.amount() == null || command.currency() == null
                || command.occurredAt() == null) {
            throw new InvalidRequestException("a complete transaction is required");
        }
        TerminalTransaction transaction;
        try {
            transaction = new TerminalTransaction(
                    command.transactionId(),
                    command.terminalId(),
                    new AccountId(command.accountId()),
                    command.amount(),
                    command.currency(),
                    command.occurredAt());
        } catch (IllegalArgumentException e) {
            throw new InvalidRequestException("the transaction is malformed");
        }
        return transactions.saveIfAbsent(transaction);
    }
}
