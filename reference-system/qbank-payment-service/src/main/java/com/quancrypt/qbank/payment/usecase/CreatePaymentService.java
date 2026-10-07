package com.quancrypt.qbank.payment.usecase;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.Caller;
import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.port.inbound.AccountAccessDeniedException;
import com.quancrypt.qbank.payment.port.inbound.AccountNotFoundException;
import com.quancrypt.qbank.payment.port.inbound.CallerNotAuthenticatedException;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentCommand;
import com.quancrypt.qbank.payment.port.inbound.CreatePaymentUseCase;
import com.quancrypt.qbank.payment.port.inbound.IdempotencyConflictException;
import com.quancrypt.qbank.payment.port.inbound.InvalidRequestException;
import com.quancrypt.qbank.payment.port.inbound.PaymentResult;
import com.quancrypt.qbank.payment.port.inbound.UpstreamUnavailableException;
import com.quancrypt.qbank.payment.port.outbound.AccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException;
import com.quancrypt.qbank.payment.port.outbound.CardTokenizer;
import com.quancrypt.qbank.payment.port.outbound.Clock;
import com.quancrypt.qbank.payment.port.outbound.IdGenerator;
import com.quancrypt.qbank.payment.port.outbound.IdempotencyStore;
import com.quancrypt.qbank.payment.port.outbound.PaymentRepository;
import java.math.BigDecimal;
import java.util.Objects;
import java.util.regex.Pattern;

/**
 * Validates the account with the caller's token, tokenizes the card and records the payment. The constructor has
 * six collaborators because each is a separate port (account, tokenizer, storage, idempotency, ids, time).
 */
public final class CreatePaymentService implements CreatePaymentUseCase {

    private static final Pattern CARD_NUMBER = Pattern.compile("[0-9]{13,19}");

    private final AccountDirectory accounts;
    private final CardTokenizer tokenizer;
    private final PaymentRepository payments;
    private final IdempotencyStore idempotency;
    private final IdGenerator ids;
    private final Clock clock;

    public CreatePaymentService(
            AccountDirectory accounts,
            CardTokenizer tokenizer,
            PaymentRepository payments,
            IdempotencyStore idempotency,
            IdGenerator ids,
            Clock clock) {
        this.accounts = Objects.requireNonNull(accounts, "accounts");
        this.tokenizer = Objects.requireNonNull(tokenizer, "tokenizer");
        this.payments = Objects.requireNonNull(payments, "payments");
        this.idempotency = Objects.requireNonNull(idempotency, "idempotency");
        this.ids = Objects.requireNonNull(ids, "ids");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    @Override
    public PaymentResult create(CreatePaymentCommand command) {
        if (command == null) {
            throw new InvalidRequestException("a request is required");
        }
        Caller caller = toCaller(command);
        AccountId accountId = validate(command);
        String key = command.idempotencyKey();
        String scope = key == null ? null : caller.username() + "|payment.create|" + key;
        String description = accountId.value() + "|" + command.amount().toPlainString() + "|" + command.currency()
                + "|" + command.cardNumber();
        if (scope != null) {
            switch (idempotency.findPayment(scope, description)) {
                case IdempotencyStore.Lookup.Replay<Payment> replay -> {
                    return toResult(replay.outcome());
                }
                case IdempotencyStore.Lookup.Conflict<Payment> conflict -> throw new IdempotencyConflictException();
                case IdempotencyStore.Lookup.Absent<Payment> absent -> { }
            }
        }
        verifyAccount(accountId, caller);
        CardToken token = tokenizer.tokenize(command.cardNumber());
        Payment payment = new Payment(
                ids.newId(), accountId, command.amount(), command.currency(), token, clock.now());
        payments.save(payment);
        if (scope != null) {
            idempotency.savePayment(scope, description, payment);
        }
        return toResult(payment);
    }

    private static AccountId validate(CreatePaymentCommand command) {
        try {
            if (command.amount() == null || command.currency() == null || command.cardNumber() == null
                    || command.accountId() == null) {
                throw new InvalidRequestException("account id, amount, currency and card number are required");
            }
            Payment.requireValidAmount(command.amount());
            Payment.requireValidCurrency(command.currency());
            if (!CARD_NUMBER.matcher(command.cardNumber()).matches()) {
                throw new InvalidRequestException("card number must be 13 to 19 digits");
            }
            return new AccountId(command.accountId());
        } catch (IllegalArgumentException e) {
            throw new InvalidRequestException("the payment request is malformed");
        }
    }

    private static Caller toCaller(CreatePaymentCommand command) {
        if (command.username() == null || command.bearerToken() == null) {
            throw new InvalidRequestException("a caller is required");
        }
        try {
            return new Caller(command.username(), command.bearerToken());
        } catch (IllegalArgumentException e) {
            throw new InvalidRequestException("a caller is required");
        }
    }

    private void verifyAccount(AccountId accountId, Caller caller) {
        try {
            accounts.findAccount(accountId, caller);
        } catch (AccountLookupException e) {
            switch (e.reason()) {
                case NOT_FOUND -> throw new AccountNotFoundException();
                case FORBIDDEN -> throw new AccountAccessDeniedException();
                case UNAUTHORIZED -> throw new CallerNotAuthenticatedException();
                case UNAVAILABLE -> throw new UpstreamUnavailableException();
            }
        }
    }

    private static PaymentResult toResult(Payment payment) {
        BigDecimal amount = payment.amount();
        return new PaymentResult(
                payment.paymentId(), payment.accountId().value(), amount, payment.currency(), payment.createdAt());
    }
}
