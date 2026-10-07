package com.quancrypt.qbank.payment.port.outbound;

import com.quancrypt.qbank.payment.domain.model.Payment;
import java.util.Optional;
import java.util.UUID;

/** Stores payments. */
public interface PaymentRepository {

    /** Stores the payment; a payment with the same id is replaced. */
    void save(Payment payment);

    Optional<Payment> findById(UUID paymentId);
}
