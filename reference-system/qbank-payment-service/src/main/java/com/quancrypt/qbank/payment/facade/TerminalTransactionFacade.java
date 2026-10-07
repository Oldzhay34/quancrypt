package com.quancrypt.qbank.payment.facade;

import com.quancrypt.qbank.payment.facade.dto.TerminalTransactionView;
import com.quancrypt.qbank.payment.facade.error.BadRequestException;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.RecordTerminalTransactionCommand;
import com.quancrypt.qbank.payment.port.inbound.RecordTerminalTransactionUseCase;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Objects;
import java.util.UUID;

/** Entry point of the MQTT listener for terminal transactions. */
public final class TerminalTransactionFacade {

    private final RecordTerminalTransactionUseCase recordTransaction;

    public TerminalTransactionFacade(RecordTerminalTransactionUseCase recordTransaction) {
        this.recordTransaction = Objects.requireNonNull(recordTransaction, "recordTransaction");
    }

    /**
     * Records the transaction.
     *
     * @return true when recorded, false when the transaction id had been recorded before
     * @throws BadRequestException when a field is malformed
     */
    public boolean record(TerminalTransactionView transaction) {
        if (transaction == null || transaction.transactionId() == null || transaction.terminalId() == null
                || transaction.accountId() == null || transaction.amount() == null || transaction.currency() == null
                || transaction.occurredAt() == null) {
            throw new BadRequestException("the transaction message is incomplete");
        }
        RecordTerminalTransactionCommand command;
        try {
            command = new RecordTerminalTransactionCommand(
                    UUID.fromString(transaction.transactionId()),
                    transaction.terminalId(),
                    transaction.accountId(),
                    new BigDecimal(transaction.amount()),
                    transaction.currency(),
                    Instant.parse(transaction.occurredAt()));
        } catch (IllegalArgumentException | DateTimeParseException e) {
            throw new BadRequestException("the transaction message is malformed");
        }
        try {
            return recordTransaction.record(command);
        } catch (InvalidRequestException e) {
            throw new BadRequestException(e.getMessage());
        }
    }
}
