package com.quancrypt.qbank.payment.unit.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.domain.model.Caller;
import com.quancrypt.qbank.payment.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.payment.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.CallerNotAuthenticatedException;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentCommand;
import com.quancrypt.qbank.payment.port.inbound.IdempotencyConflictException;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.PaymentResult;
import com.quancrypt.qbank.payment.port.inbound.UpstreamUnavailableException;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException.Reason;
import com.quancrypt.qbank.payment.support.Fakes.FakeAccountDirectory;
import com.quancrypt.qbank.payment.support.Fakes.FakeCardTokenizer;
import com.quancrypt.qbank.payment.support.Fakes.FakeIdempotencyStore;
import com.quancrypt.qbank.payment.support.Fakes.FakePaymentRepository;
import com.quancrypt.qbank.payment.support.Fakes.FixedClock;
import com.quancrypt.qbank.payment.support.Fakes.SequentialIdGenerator;
import com.quancrypt.qbank.payment.usecase.CreatePaymentService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CreatePaymentServiceTest {

    private static final Instant NOW = Instant.parse("2026-10-07T10:00:00Z");
    private static final String CARD = "4111111111111111";

    private FakeAccountDirectory accounts;
    private FakePaymentRepository payments;
    private CreatePaymentService service;

    @BeforeEach
    void setUp() {
        accounts = new FakeAccountDirectory();
        payments = new FakePaymentRepository();
        service = new CreatePaymentService(
                accounts, new FakeCardTokenizer(), payments, new FakeIdempotencyStore(),
                new SequentialIdGenerator(), new FixedClock(NOW));
    }

    private static CreatePaymentCommand command(String key, String accountId, String amount, String card) {
        return new CreatePaymentCommand(
                "demo1", "jwt-of-demo1", key, accountId, amount == null ? null : new BigDecimal(amount), "TRY", card);
    }

    @Test
    void validatesTheAccountWithTheCallersTokenThenRecordsThePayment() {
        PaymentResult result = service.create(command(null, "acc-001", "12.50", CARD));

        assertThat(result.paymentId()).isEqualTo(new UUID(0, 1));
        assertThat(result.accountId()).isEqualTo("acc-001");
        assertThat(result.amount().toPlainString()).isEqualTo("12.50");
        assertThat(result.createdAt()).isEqualTo(NOW);
        assertThat(accounts.calls()).hasSize(1);
        assertThat(accounts.calls().get(0).caller()).isEqualTo(new Caller("demo1", "jwt-of-demo1"));
        assertThat(payments.findById(result.paymentId())).isPresent();
        assertThat(payments.findById(result.paymentId()).orElseThrow().cardToken().value())
                .isEqualTo("fake-token:1111111111111114");
    }

    @Test
    void theResultNeverCarriesTheCardNumberOrItsToken() {
        PaymentResult result = service.create(command(null, "acc-001", "12.50", CARD));

        assertThat(result.toString()).doesNotContain(CARD).doesNotContain("fake-token");
    }

    @Test
    void accountFailuresBecomeUseCaseErrorsAndNothingIsStored() {
        accounts.failFor("acc-404", Reason.NOT_FOUND).failFor("acc-403", Reason.FORBIDDEN)
                .failFor("acc-401", Reason.UNAUTHORIZED).failFor("acc-503", Reason.UNAVAILABLE);

        assertThatThrownBy(() -> service.create(command(null, "acc-404", "1.00", CARD)))
                .isInstanceOf(AccountNotFoundException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-403", "1.00", CARD)))
                .isInstanceOf(AccountAccessDeniedException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-401", "1.00", CARD)))
                .isInstanceOf(CallerNotAuthenticatedException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-503", "1.00", CARD)))
                .isInstanceOf(UpstreamUnavailableException.class);
        assertThat(payments.size()).isZero();
    }

    @Test
    void malformedRequestsAreRejectedBeforeTheAccountServiceIsCalled() {
        assertThatThrownBy(() -> service.create(null)).isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-001", "-1.00", CARD)))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-001", "1.234", CARD)))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-001", null, CARD)))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-001", "1.00", "1234")))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(command(null, "acc-001", "1.00", "4111-1111-1111-1111")))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(command(null, " ", "1.00", CARD)))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(new CreatePaymentCommand(
                " ", "token", null, "acc-001", BigDecimal.ONE, "TRY", CARD)))
                .isInstanceOf(InvalidRequestException.class);
        assertThatThrownBy(() -> service.create(new CreatePaymentCommand(
                "demo1", "token", null, "acc-001", BigDecimal.ONE, "try", CARD)))
                .isInstanceOf(InvalidRequestException.class);
        assertThat(accounts.calls()).isEmpty();
    }

    @Test
    void theSameKeyAndRequestReplaysTheFirstPaymentWithoutANewAccountCall() {
        PaymentResult first = service.create(command("key-1", "acc-001", "12.50", CARD));
        PaymentResult second = service.create(command("key-1", "acc-001", "12.50", CARD));

        assertThat(second).isEqualTo(first);
        assertThat(payments.size()).isEqualTo(1);
        assertThat(accounts.calls()).hasSize(1);
    }

    @Test
    void theSameKeyWithADifferentRequestIsAConflict() {
        service.create(command("key-1", "acc-001", "12.50", CARD));

        assertThatThrownBy(() -> service.create(command("key-1", "acc-001", "13.50", CARD)))
                .isInstanceOf(IdempotencyConflictException.class);
        assertThat(payments.size()).isEqualTo(1);
    }

    @Test
    void theSameKeyFromAnotherCallerIsAnotherRequest() {
        service.create(command("key-1", "acc-001", "12.50", CARD));

        PaymentResult other = service.create(new CreatePaymentCommand(
                "demo2", "jwt-of-demo2", "key-1", "acc-002", new BigDecimal("12.50"), "TRY", CARD));

        assertThat(other.paymentId()).isEqualTo(new UUID(0, 2));
        assertThat(payments.size()).isEqualTo(2);
    }

    @Test
    void withoutAKeyEveryCallCreatesANewPayment() {
        PaymentResult first = service.create(command(null, "acc-001", "12.50", CARD));
        PaymentResult second = service.create(command(null, "acc-001", "12.50", CARD));

        assertThat(second.paymentId()).isNotEqualTo(first.paymentId());
    }

    @Test
    void theCommandNeverPrintsTheCardNumberOrTheToken() {
        String text = command("k", "acc-001", "1.00", CARD).toString();

        assertThat(text).doesNotContain(CARD).doesNotContain("jwt-of-demo1");
    }
}
