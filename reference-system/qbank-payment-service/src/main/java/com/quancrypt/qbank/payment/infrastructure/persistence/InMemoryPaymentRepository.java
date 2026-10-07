package com.quancrypt.qbank.payment.infrastructure.persistence;

import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.port.outbound.PaymentRepository;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** Holds payments in memory; they are lost when the service stops. */
public final class InMemoryPaymentRepository implements PaymentRepository {

    private final Map<UUID, Payment> payments = new ConcurrentHashMap<>();

    @Override
    public void save(Payment payment) {
        payments.put(payment.paymentId(), payment);
    }

    @Override
    public Optional<Payment> findById(UUID paymentId) {
        return Optional.ofNullable(payments.get(paymentId));
    }
}
