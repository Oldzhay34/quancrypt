package com.quancrypt.qbank.payment.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.Caller;
import com.quancrypt.qbank.payment.domain.model.CardToken;
import com.quancrypt.qbank.payment.domain.model.Payment;
import com.quancrypt.qbank.payment.domain.model.Receipt;
import com.quancrypt.qbank.payment.domain.model.ReceiptSignature;
import com.quancrypt.qbank.payment.domain.model.TerminalTransaction;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class DomainModelTest {

    private static final UUID ID = UUID.fromString("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11");
    private static final AccountId ACCOUNT = new AccountId("acc-001");
    private static final Instant NOW = Instant.parse("2026-10-07T10:15:30Z");

    @Test
    void accountIdIsOneToSixtyFourCharactersFromTheAllowedSet() {
        assertThat(new AccountId("Acc_001.x-y").value()).isEqualTo("Acc_001.x-y");
        assertThatThrownBy(() -> new AccountId("")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AccountId("acc/001")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AccountId("acc 001")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AccountId("acc$001")).isInstanceOf(IllegalArgumentException.class);
        assertThat(new AccountId("a".repeat(64)).value()).hasSize(64);
        assertThatThrownBy(() -> new AccountId(" ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AccountId("a".repeat(65))).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void secretsNeverAppearInToString() {
        assertThat(new CardToken("super-secret-token").toString()).doesNotContain("super-secret-token");
        assertThat(new Caller("demo1", "eyJ.secret.jwt").toString()).doesNotContain("eyJ").contains("demo1");
    }

    @Test
    void aCallerNeedsANameAndAToken() {
        assertThatThrownBy(() -> new Caller(" ", "token")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Caller("demo1", " ")).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void aPaymentNormalizesTheAmountAndTruncatesTheTimeToSeconds() {
        Payment payment = new Payment(
                ID, ACCOUNT, new BigDecimal("12.5"), "TRY", new CardToken("t"), Instant.parse("2026-10-07T10:15:30.987Z"));

        assertThat(payment.amount().toPlainString()).isEqualTo("12.50");
        assertThat(payment.createdAt()).isEqualTo(NOW);
    }

    @Test
    void aPaymentRejectsInvalidAmountsAndCurrencies() {
        CardToken token = new CardToken("t");
        assertThatThrownBy(() -> new Payment(ID, ACCOUNT, new BigDecimal("-1.00"), "TRY", token, NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Payment(ID, ACCOUNT, new BigDecimal("1.234"), "TRY", token, NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Payment(ID, ACCOUNT, BigDecimal.TEN, "try", token, NOW))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void theReceiptSigningInputIsCompactJsonInAFixedFieldOrder() {
        Receipt receipt = new Receipt(ID, ACCOUNT, new BigDecimal("12.50"), "TRY", NOW);

        assertThat(receipt.signingInput()).isEqualTo(
                "{\"paymentId\":\"3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11\",\"accountId\":\"acc-001\","
                        + "\"amount\":\"12.50\",\"currency\":\"TRY\",\"issuedAt\":\"2026-10-07T10:15:30Z\"}");
    }

    /** Since D-105 an account id cannot carry a character that JSON would have to escape; the escaping stays as a guard. */
    @Test
    void noCharacterThatJsonWouldEscapeCanReachTheReceiptSigningInput() {
        for (String id : new String[] {"a\"b", "a\\b", "a\nb", "a\u0001b", "a\tb"}) {
            assertThatThrownBy(() -> new AccountId(id)).as(id).isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void theReceiptSigningInputHasNoWhitespaceOutsideValues() {
        Receipt receipt = new Receipt(ID, ACCOUNT, BigDecimal.ZERO, "TRY", NOW);

        assertThat(receipt.signingInput()).doesNotContain(" ", "\n", "\t");
        assertThat(receipt.signingInput().indexOf("paymentId"))
                .isLessThan(receipt.signingInput().indexOf("accountId"));
    }

    @Test
    void aReceiptSignatureNeedsAllParts() {
        assertThatThrownBy(() -> new ReceiptSignature("SHA1withRSA", " ", "sig")).isInstanceOf(IllegalArgumentException.class);
        assertThat(new ReceiptSignature("SHA1withRSA", "kid", "sig").algorithm()).isEqualTo("SHA1withRSA");
    }

    @Test
    void aTerminalTransactionValidatesItsFields() {
        assertThat(new TerminalTransaction(ID, "terminal-001", ACCOUNT, new BigDecimal("5"), "TRY", NOW).amount().toPlainString())
                .isEqualTo("5.00");
        assertThatThrownBy(() -> new TerminalTransaction(ID, " ", ACCOUNT, BigDecimal.ONE, "TRY", NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new TerminalTransaction(ID, "t", ACCOUNT, BigDecimal.ONE, "tr", NOW))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new TerminalTransaction(ID, "t", ACCOUNT, new BigDecimal("1.001"), "TRY", NOW))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
