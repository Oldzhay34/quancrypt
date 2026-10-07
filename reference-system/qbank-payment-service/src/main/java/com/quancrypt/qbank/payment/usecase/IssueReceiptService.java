package com.quancrypt.qbank.payment.usecase;

import com.quancrypt.qbank.payment.domain.model.IssuedReceipt;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.domain.model.Receipt;
import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;
import com.quancrypt.qbank.payment.port.inbound.IdempotencyConflictException;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.IssueReceiptCommand;
import com.quancrypt.qbank.payment.port.inbound.IssueReceiptUseCase;
import com.quancrypt.qbank.payment.port.inbound.PaymentNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.SignedReceiptResult;
import com.quancrypt.qbank.payment.port.outbound.Clock;
import com.quancrypt.qbank.payment.port.outbound.IdempotencyStore;
import com.quancrypt.qbank.payment.port.outbound.PaymentRepository;
import com.quancrypt.qbank.payment.port.outbound.ReceiptSigner;
import java.util.Objects;

/** Builds the receipt of a payment and has it signed. */
public final class IssueReceiptService implements IssueReceiptUseCase {

    private final PaymentRepository payments;
    private final ReceiptSigner signer;
    private final IdempotencyStore idempotency;
    private final Clock clock;

    public IssueReceiptService(
            PaymentRepository payments, ReceiptSigner signer, IdempotencyStore idempotency, Clock clock) {
        this.payments = Objects.requireNonNull(payments, "payments");
        this.signer = Objects.requireNonNull(signer, "signer");
        this.idempotency = Objects.requireNonNull(idempotency, "idempotency");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    @Override
    public SignedReceiptResult issue(IssueReceiptCommand command) {
        if (command == null || command.username() == null || command.username().isBlank() || command.paymentId() == null) {
            throw new InvalidRequestException("a caller and a payment id are required");
        }
        Payment payment = payments.findById(command.paymentId()).orElseThrow(PaymentNotFoundException::new);
        String key = command.idempotencyKey();
        String scope = key == null ? null : command.username() + "|receipt.issue|" + key;
        String description = payment.paymentId().toString();
        if (scope != null) {
            switch (idempotency.findReceipt(scope, description)) {
                case IdempotencyStore.Lookup.Replay<IssuedReceipt> replay -> {
                    return toResult(replay.outcome());
                }
                case IdempotencyStore.Lookup.Conflict<IssuedReceipt> conflict -> throw new IdempotencyConflictException();
                case IdempotencyStore.Lookup.Absent<IssuedReceipt> absent -> { }
            }
        }
        Receipt receipt = new Receipt(
                payment.paymentId(), payment.accountId(), payment.amount(), payment.currency(), clock.now());
        ReceiptSignature signature = signer.sign(receipt.signingInput());
        IssuedReceipt issued = new IssuedReceipt(receipt, signature);
        if (scope != null) {
            idempotency.saveReceipt(scope, description, issued);
        }
        return toResult(issued);
    }

    private static SignedReceiptResult toResult(IssuedReceipt issued) {
        Receipt receipt = issued.receipt();
        ReceiptSignature signature = issued.signature();
        return new SignedReceiptResult(
                receipt.paymentId(),
                new SignedReceiptResult.ReceiptData(
                        receipt.paymentId(), receipt.accountId().value(), receipt.amount(), receipt.currency(),
                        receipt.issuedAt()),
                signature.signature(),
                signature.algorithm(),
                signature.keyId());
    }
}
