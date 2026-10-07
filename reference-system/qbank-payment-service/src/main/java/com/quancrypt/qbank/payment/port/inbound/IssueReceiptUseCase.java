package com.quancrypt.qbank.payment.port.inbound;

/** Issues a signed receipt for a payment. */
public interface IssueReceiptUseCase {

    /**
     * Issues the receipt.
     *
     * @throws InvalidRequestException when the request is malformed
     * @throws PaymentNotFoundException when the payment does not exist
     * @throws IdempotencyConflictException when the idempotency key was used with a different request
     */
    SignedReceiptResult issue(IssueReceiptCommand command);
}
