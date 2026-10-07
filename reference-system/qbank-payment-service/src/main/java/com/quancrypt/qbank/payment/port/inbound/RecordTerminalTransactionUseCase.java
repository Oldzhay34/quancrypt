package com.quancrypt.qbank.payment.port.inbound;

/** Records a transaction that a field terminal reported. */
public interface RecordTerminalTransactionUseCase {

    /**
     * Records the transaction; a transaction id seen before is ignored.
     *
     * @return true when the transaction was recorded, false when it was a duplicate
     * @throws InvalidRequestException when the transaction is malformed
     */
    boolean record(RecordTerminalTransactionCommand command);
}
