package com.quancrypt.qbank.payment.domain.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

/** The receipt of a payment. {@link #signingInput()} is the exact text that gets signed (D-93). */
public record Receipt(UUID paymentId, AccountId accountId, BigDecimal amount, String currency, Instant issuedAt) {

    private static final Pattern CURRENCY = Pattern.compile("[A-Z]{3}");

    public Receipt {
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(accountId, "accountId");
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(issuedAt, "issuedAt");
        if (!CURRENCY.matcher(currency).matches()) {
            throw new IllegalArgumentException("currency must be a three letter upper case code");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative");
        }
        try {
            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException e) {
            throw new IllegalArgumentException("amount must have at most two fractional digits");
        }
        issuedAt = issuedAt.truncatedTo(ChronoUnit.SECONDS);
    }

    /**
     * Compact JSON with the fixed field order paymentId, accountId, amount, currency, issuedAt and no whitespace.
     * The signature is computed over the UTF-8 bytes of this text.
     */
    public String signingInput() {
        return "{\"paymentId\":" + quote(paymentId.toString())
                + ",\"accountId\":" + quote(accountId.value())
                + ",\"amount\":" + quote(amount.toPlainString())
                + ",\"currency\":" + quote(currency)
                + ",\"issuedAt\":" + quote(issuedAt.toString()) + "}";
    }

    private static String quote(String value) {
        StringBuilder json = new StringBuilder(value.length() + 2).append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> json.append("\\\"");
                case '\\' -> json.append("\\\\");
                case '\n' -> json.append("\\n");
                case '\r' -> json.append("\\r");
                case '\t' -> json.append("\\t");
                case '\b' -> json.append("\\b");
                case '\f' -> json.append("\\f");
                default -> {
                    if (c < 0x20) {
                        json.append(String.format("\\u%04x", (int) c));
                    } else {
                        json.append(c);
                    }
                }
            }
        }
        return json.append('"').toString();
    }
}
