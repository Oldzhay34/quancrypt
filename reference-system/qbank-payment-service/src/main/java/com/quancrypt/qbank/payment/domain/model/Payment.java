package com.quancrypt.qbank.payment.domain.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

/** A payment: the amount for an account and the token of the card that paid it. */
public record Payment(
        UUID paymentId, AccountId accountId, BigDecimal amount, String currency, CardToken cardToken, Instant createdAt) {

    private static final Pattern CURRENCY = Pattern.compile("[A-Z]{3}");

    public Payment {
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(accountId, "accountId");
        Objects.requireNonNull(cardToken, "cardToken");
        Objects.requireNonNull(createdAt, "createdAt");
        amount = requireValidAmount(amount);
        requireValidCurrency(currency);
        createdAt = createdAt.truncatedTo(ChronoUnit.SECONDS);
    }

    /** Checks and normalizes an amount: not negative, at most two fractional digits; the result has exactly two. */
    public static BigDecimal requireValidAmount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
        try {
            return amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException e) {
            throw new IllegalArgumentException("amount must have at most two fractional digits");
        }
    }

    /** Checks an ISO 4217 style currency code: three upper case letters. */
    public static void requireValidCurrency(String currency) {
        Objects.requireNonNull(currency, "currency");
        if (!CURRENCY.matcher(currency).matches()) {
            throw new IllegalArgumentException("currency must be a three letter upper case code");
        }
    }
}
