package com.quancrypt.qbank.payment.port.inbound;

import java.util.UUID;

/** Returns a payment. */
public interface GetPaymentUseCase {

    /**
     * Returns the payment.
     *
     * @throws PaymentNotFoundException when the payment does not exist
     */
    PaymentResult get(UUID paymentId);
}
