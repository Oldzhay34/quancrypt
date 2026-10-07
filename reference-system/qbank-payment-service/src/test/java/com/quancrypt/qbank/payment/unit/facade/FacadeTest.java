package com.quancrypt.qbank.payment.unit.facade;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.facade.PaymentFacade;
import com.quancrypt.qbank.payment.facade.TerminalTransactionFacade;
import com.quancrypt.qbank.payment.facade.dto.CallerView;
import com.quancrypt.qbank.payment.facade.dto.NewPaymentView;
import com.quancrypt.qbank.payment.facade.dto.PaymentView;
import com.quancrypt.qbank.payment.facade.dto.SignedReceiptView;
import com.quancrypt.qbank.payment.facade.dto.TerminalTransactionView;
import com.quancrypt.qbank.payment.facade.error.BadRequestException;
import com.quancrypt.qbank.payment.facade.error.ConflictException;
import com.quancrypt.qbank.payment.facade.error.ForbiddenException;
import com.quancrypt.qbank.payment.facade.error.ResourceNotFoundException;
import com.quancrypt.qbank.payment.facade.error.ServiceUnavailableException;
import com.quancrypt.qbank.payment.facade.error.UnauthorizedException;
import com.quancrypt.qbank.payment.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.payment.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.CallerNotAuthenticatedException;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentCommand;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.GetPaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.IdempotencyConflictException;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.IssueReceiptUseCase;
import com.quancrypt.qbank.payment.port.inbound.PaymentNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.PaymentResult;
import com.quancrypt.qbank.payment.port.inbound.SignedReceiptResult;
import com.quancrypt.qbank.payment.port.inbound.UpstreamUnavailableException;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class FacadeTest {

    private static final UUID ID = new UUID(0, 5);
    private static final Instant NOW = Instant.parse("2026-10-07T10:00:00Z");
    private static final CallerView CALLER = new CallerView("demo1", "jwt");
    private static final NewPaymentView NEW_PAYMENT = new NewPaymentView("acc-001", "12.50", "TRY", "4111111111111111");

    private static PaymentFacade facade(CreatePaymentUseCase create, GetPaymentUseCase get, IssueReceiptUseCase receipt) {
        return new PaymentFacade(create, get, receipt);
    }

    private static PaymentFacade creating(CreatePaymentUseCase create) {
        return facade(create, id -> null, command -> null);
    }

    @Test
    void createPaymentPassesTheCallerAndFieldsAndRendersTheResultAsText() {
        AtomicReference<CreatePaymentCommand> seen = new AtomicReference<>();
        PaymentFacade facade = creating(command -> {
            seen.set(command);
            return new PaymentResult(ID, "acc-001", new BigDecimal("12.50"), "TRY", NOW);
        });

        PaymentView view = facade.createPayment(CALLER, "key-1", NEW_PAYMENT);

        assertThat(view).isEqualTo(new PaymentView(ID.toString(), "acc-001", "12.50", "TRY", "2026-10-07T10:00:00Z"));
        assertThat(seen.get().username()).isEqualTo("demo1");
        assertThat(seen.get().bearerToken()).isEqualTo("jwt");
        assertThat(seen.get().idempotencyKey()).isEqualTo("key-1");
        assertThat(seen.get().amount()).isEqualByComparingTo("12.50");
    }

    @Test
    void createPaymentTranslatesEveryUseCaseError() {
        assertThatThrownBy(() -> creating(c -> {
            throw new InvalidRequestException("x");
        }).createPayment(CALLER, null, NEW_PAYMENT)).isInstanceOf(BadRequestException.class);
        assertThatThrownBy(() -> creating(c -> {
            throw new CallerNotAuthenticatedException();
        }).createPayment(CALLER, null, NEW_PAYMENT)).isInstanceOf(UnauthorizedException.class);
        assertThatThrownBy(() -> creating(c -> {
            throw new AccountAccessDeniedException();
        }).createPayment(CALLER, null, NEW_PAYMENT)).isInstanceOf(ForbiddenException.class);
        assertThatThrownBy(() -> creating(c -> {
            throw new AccountNotFoundException();
        }).createPayment(CALLER, null, NEW_PAYMENT)).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> creating(c -> {
            throw new IdempotencyConflictException();
        }).createPayment(CALLER, null, NEW_PAYMENT)).isInstanceOf(ConflictException.class);
        assertThatThrownBy(() -> creating(c -> {
            throw new UpstreamUnavailableException();
        }).createPayment(CALLER, null, NEW_PAYMENT)).isInstanceOf(ServiceUnavailableException.class);
    }

    @Test
    void anAmountThatIsNotANumberIsABadRequest() {
        PaymentFacade facade = creating(c -> null);

        assertThatThrownBy(() -> facade.createPayment(CALLER, null, new NewPaymentView("a", "abc", "TRY", "4111111111111111")))
                .isInstanceOf(BadRequestException.class);
    }

    @Test
    void getPaymentRendersTheResultAndTreatsNonUuidIdsAsNotFound() {
        PaymentFacade facade = facade(
                create -> null, id -> new PaymentResult(id, "acc-001", new BigDecimal("1.00"), "TRY", NOW), r -> null);

        assertThat(facade.getPayment(ID.toString()).paymentId()).isEqualTo(ID.toString());
        assertThatThrownBy(() -> facade.getPayment("not-a-uuid")).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> facade.getPayment(null)).isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void getPaymentTranslatesNotFound() {
        PaymentFacade facade = facade(create -> null, id -> {
            throw new PaymentNotFoundException();
        }, r -> null);

        assertThatThrownBy(() -> facade.getPayment(ID.toString())).isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void issueReceiptRendersTheSignedReceiptAndTranslatesErrors() {
        PaymentFacade ok = facade(create -> null, id -> null, command -> new SignedReceiptResult(
                ID,
                new SignedReceiptResult.ReceiptData(ID, "acc-001", new BigDecimal("12.50"), "TRY", NOW),
                "c2ln", "SHA1withRSA", "kid"));

        SignedReceiptView view = ok.issueReceipt(CALLER, null, ID.toString());

        assertThat(view.algorithm()).isEqualTo("SHA1withRSA");
        assertThat(view.receipt().amount()).isEqualTo("12.50");
        assertThat(view.receipt().issuedAt()).isEqualTo("2026-10-07T10:00:00Z");
        assertThatThrownBy(() -> ok.issueReceipt(CALLER, null, "nope")).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> facade(create -> null, id -> null, c -> {
            throw new PaymentNotFoundException();
        }).issueReceipt(CALLER, null, ID.toString())).isInstanceOf(ResourceNotFoundException.class);
        assertThatThrownBy(() -> facade(create -> null, id -> null, c -> {
            throw new IdempotencyConflictException();
        }).issueReceipt(CALLER, "k", ID.toString())).isInstanceOf(ConflictException.class);
        assertThatThrownBy(() -> facade(create -> null, id -> null, c -> {
            throw new InvalidRequestException("x");
        }).issueReceipt(CALLER, "k", ID.toString())).isInstanceOf(BadRequestException.class);
    }

    @Test
    void terminalTransactionsAreParsedAndRecorded() {
        TerminalTransactionFacade facade = new TerminalTransactionFacade(command -> true);

        assertThat(facade.record(new TerminalTransactionView(
                ID.toString(), "terminal-001", "acc-001", "5.00", "TRY", "2026-10-07T10:00:00Z"))).isTrue();
    }

    @Test
    void malformedTerminalTransactionFieldsAreABadRequest() {
        TerminalTransactionFacade facade = new TerminalTransactionFacade(command -> true);

        for (TerminalTransactionView bad : new TerminalTransactionView[] {
            new TerminalTransactionView("nope", "t", "a", "5.00", "TRY", "2026-10-07T10:00:00Z"),
            new TerminalTransactionView(ID.toString(), "t", "a", "five", "TRY", "2026-10-07T10:00:00Z"),
            new TerminalTransactionView(ID.toString(), "t", "a", "5.00", "TRY", "yesterday"),
            new TerminalTransactionView(null, "t", "a", "5.00", "TRY", "2026-10-07T10:00:00Z"),
        }) {
            assertThatThrownBy(() -> facade.record(bad)).isInstanceOf(BadRequestException.class);
        }
    }

    @Test
    void useCaseRejectionOfATerminalTransactionIsABadRequest() {
        TerminalTransactionFacade facade = new TerminalTransactionFacade(command -> {
            throw new InvalidRequestException("x");
        });

        assertThatThrownBy(() -> facade.record(new TerminalTransactionView(
                ID.toString(), "t", "a", "5.00", "TRY", "2026-10-07T10:00:00Z"))).isInstanceOf(BadRequestException.class);
    }
}
