package com.quancrypt.qbank.payment.usecase;

import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.port.inbound.GetPaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.PaymentNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.PaymentResult;
import com.quancrypt.qbank.payment.port.outbound.PaymentRepository;
import java.util.Objects;
import java.util.UUID;

/** Returns a payment by id. */
public final class GetPaymentService implements GetPaymentUseCase {

    private final PaymentRepository payments;

    public GetPaymentService(PaymentRepository payments) {
        this.payments = Objects.requireNonNull(payments, "payments");
    }

    @Override
    public PaymentResult get(UUID paymentId) {
        if (paymentId == null) {
            throw new PaymentNotFoundException();
        }
        Payment payment = payments.findById(paymentId).orElseThrow(PaymentNotFoundException::new);
        return new PaymentResult(
                payment.paymentId(), payment.accountId().value(), payment.amount(), payment.currency(), payment.createdAt());
    }
}
