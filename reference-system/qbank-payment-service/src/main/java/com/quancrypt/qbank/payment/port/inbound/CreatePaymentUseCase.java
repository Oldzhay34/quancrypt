package com.quancrypt.qbank.payment.port.inbound;

/** Creates a payment: validates the account, tokenizes the card and records the payment. */
public interface CreatePaymentUseCase {

    /**
     * Creates the payment.
     *
     * @throws InvalidRequestException when the request is malformed
     * @throws AccountNotFoundException when the account does not exist
     * @throws AccountAccessDeniedException when the caller does not own the account
     * @throws CallerNotAuthenticatedException when the account service rejects the caller's token
     * @throws UpstreamUnavailableException when the account service cannot be reached
     * @throws IdempotencyConflictException when the idempotency key was used with a different request
     */
    PaymentResult create(CreatePaymentCommand command);
}
