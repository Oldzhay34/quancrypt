package com.quancrypt.qbank.payment.unit.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.port.inbound.IdempotencyConflictException;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.IssueReceiptCommand;
import com.quancrypt.qbank.payment.port.inbound.PaymentNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.PaymentResult;
import com.quancrypt.qbank.payment.port.inbound.RecordTerminalTransactionCommand;
import com.quancrypt.qbank.payment.port.inbound.SignedReceiptResult;
import com.quancrypt.qbank.payment.support.Fakes.FakeIdempotencyStore;
import com.quancrypt.qbank.payment.support.Fakes.FakePaymentRepository;
import com.quancrypt.qbank.payment.support.Fakes.FakeReceiptSigner;
import com.quancrypt.qbank.payment.support.Fakes.FakeTerminalTransactionRepository;
import com.quancrypt.qbank.payment.support.Fakes.FixedClock;
import com.quancrypt.qbank.payment.usecase.GetPaymentService;
import com.quancrypt.qbank.payment.usecase.IssueReceiptService;
import com.quancrypt.qbank.payment.usecase.RecordTerminalTransactionService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class OtherUseCasesTest {

    private static final UUID PAYMENT_ID = new UUID(0, 7);
    private static final Instant NOW = Instant.parse("2026-10-07T10:00:00Z");

    private FakePaymentRepository payments;
    private FakeReceiptSigner signer;
    private IssueReceiptService receipts;

    @BeforeEach
    void setUp() {
        payments = new FakePaymentRepository();
        payments.save(new Payment(
                PAYMENT_ID, new AccountId("acc-001"), new BigDecimal("12.50"), "TRY", new CardToken("tok"),
                Instant.parse("2026-10-07T09:00:00Z")));
        signer = new FakeReceiptSigner();
        receipts = new IssueReceiptService(payments, signer, new FakeIdempotencyStore(), new FixedClock(NOW));
    }

    @Test
    void getPaymentReturnsTheStoredPaymentWithoutSecrets() {
        PaymentResult result = new GetPaymentService(payments).get(PAYMENT_ID);

        assertThat(result.accountId()).isEqualTo("acc-001");
        assertThat(result.amount().toPlainString()).isEqualTo("12.50");
        assertThat(result.toString()).doesNotContain("tok");
    }

    @Test
    void getPaymentFailsForUnknownOrMissingIds() {
        GetPaymentService service = new GetPaymentService(payments);

        assertThatThrownBy(() -> service.get(new UUID(0, 99))).isInstanceOf(PaymentNotFoundException.class);
        assertThatThrownBy(() -> service.get(null)).isInstanceOf(PaymentNotFoundException.class);
    }

    @Test
    void issueReceiptSignsTheCompactJsonOfTheReceiptAndReturnsTheSignature() {
        SignedReceiptResult result = receipts.issue(new IssueReceiptCommand("demo1", null, PAYMENT_ID));

        assertThat(signer.signed()).containsExactly(
                "{\"paymentId\":\"00000000-0000-0000-0000-000000000007\",\"accountId\":\"acc-001\","
                        + "\"amount\":\"12.50\",\"currency\":\"TRY\",\"issuedAt\":\"2026-10-07T10:00:00Z\"}");
        assertThat(result.algorithm()).isEqualTo("SHA1withRSA");
        assertThat(result.keyId()).isEqualTo("fake-key-id");
        assertThat(result.receipt().issuedAt()).isEqualTo(NOW);
        assertThat(result.receipt().amount().toPlainString()).isEqualTo("12.50");
    }

    @Test
    void issueReceiptFailsForUnknownPaymentsAndMissingInput() {
        assertThatThrownBy(() -> receipts.issue(new IssueReceiptCommand("demo1", null, new UUID(0, 99))))
                .isInstanceOf(PaymentNotFoundException.class);
        assertThatThrownBy(() -> receipts.issue(new IssueReceiptCommand("demo1", null, null)))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> receipts.issue(new IssueReceiptCommand(" ", null, PAYMENT_ID)))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> receipts.issue(null)).isInstanceOf(InvalidRequestException.class);
    }

    @Test
    void issueReceiptWithTheSameKeyReplaysTheSameSignedReceipt() {
        SignedReceiptResult first = receipts.issue(new IssueReceiptCommand("demo1", "k1", PAYMENT_ID));
        SignedReceiptResult second = receipts.issue(new IssueReceiptCommand("demo1", "k1", PAYMENT_ID));

        assertThat(second).isEqualTo(first);
        assertThat(signer.signed()).hasSize(1);
    }

    @Test
    void issueReceiptWithTheSameKeyForAnotherPaymentIsAConflict() {
        payments.save(new Payment(
                new UUID(0, 8), new AccountId("acc-001"), BigDecimal.ONE, "TRY", new CardToken("t"), NOW));
        receipts.issue(new IssueReceiptCommand("demo1", "k1", PAYMENT_ID));

        assertThatThrownBy(() -> receipts.issue(new IssueReceiptCommand("demo1", "k1", new UUID(0, 8))))
                .isInstanceOf(IdempotencyConflictException.class);
    }

    @Test
    void withoutAKeyEveryReceiptCallSignsAgain() {
        receipts.issue(new IssueReceiptCommand("demo1", null, PAYMENT_ID));
        receipts.issue(new IssueReceiptCommand("demo1", null, PAYMENT_ID));

        assertThat(signer.signed()).hasSize(2);
    }

    @Test
    void recordingATerminalTransactionStoresItOnceAndIgnoresDuplicates() {
        FakeTerminalTransactionRepository repository = new FakeTerminalTransactionRepository();
        RecordTerminalTransactionService service = new RecordTerminalTransactionService(repository);
        RecordTerminalTransactionCommand command = new RecordTerminalTransactionCommand(
                new UUID(0, 1), "terminal-001", "acc-001", new BigDecimal("5.00"), "TRY", NOW);

        assertThat(service.record(command)).isTrue();
        assertThat(service.record(command)).isFalse();
        assertThat(repository.findById(new UUID(0, 1))).isPresent();
    }

    @Test
    void theFirstRecordOfADuplicateTransactionIsKept() {
        FakeTerminalTransactionRepository repository = new FakeTerminalTransactionRepository();
        RecordTerminalTransactionService service = new RecordTerminalTransactionService(repository);
        service.record(new RecordTerminalTransactionCommand(
                new UUID(0, 1), "terminal-001", "acc-001", new BigDecimal("5.00"), "TRY", NOW));

        service.record(new RecordTerminalTransactionCommand(
                new UUID(0, 1), "terminal-001", "acc-001", new BigDecimal("99.00"), "TRY", NOW));

        assertThat(repository.findById(new UUID(0, 1)).orElseThrow().amount().toPlainString()).isEqualTo("5.00");
    }

    @Test
    void malformedTerminalTransactionsAreRejected() {
        RecordTerminalTransactionService service = new RecordTerminalTransactionService(new FakeTerminalTransactionRepository());

        assertThatThrownBy(() -> service.record(null)).isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.record(new RecordTerminalTransactionCommand(
                new UUID(0, 1), " ", "acc-001", BigDecimal.ONE, "TRY", NOW))).isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.record(new RecordTerminalTransactionCommand(
                new UUID(0, 1), "t", null, BigDecimal.ONE, "TRY", NOW))).isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.record(new RecordTerminalTransactionCommand(
                new UUID(0, 1), "t", "acc-001", BigDecimal.ONE, "tr", NOW))).isInstanceOf(InvalidRequestException.class);
    }
}
