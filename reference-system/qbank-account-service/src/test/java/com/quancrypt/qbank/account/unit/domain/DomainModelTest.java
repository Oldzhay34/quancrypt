package com.quancrypt.qbank.account.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.domain.model.Account;
import com.quancrypt.qbank.account.domain.model.AccountId;
import com.quancrypt.qbank.account.domain.model.PasswordHash;
import com.quancrypt.qbank.account.domain.model.UserCredential;
import com.quancrypt.qbank.account.domain.model.VerificationKey;
import java.math.BigDecimal;
import java.math.BigInteger;
import org.junit.jupiter.api.Test;

class DomainModelTest {

    private static final AccountId ID = new AccountId("acc-001");

    @Test
    void accountIdAcceptsOneToSixtyFourCharacters() {
        assertThat(new AccountId("a").value()).isEqualTo("a");
        assertThat(new AccountId("a".repeat(64)).value()).hasSize(64);
    }

    @Test
    void accountIdRejectsBlankTooLongAndNull() {
        assertThatThrownBy(() -> new AccountId(" ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AccountId("")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AccountId("a".repeat(65))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AccountId(null)).isInstanceOf(NullPointerException.class);
    }

    @Test
    void accountNormalizesBalanceToTwoFractionalDigits() {
        Account account = new Account(ID, "Demo User 1", "TRY", new BigDecimal("1000"));
        assertThat(account.balance().toPlainString()).isEqualTo("1000.00");
    }

    @Test
    void accountRejectsInvalidValues() {
        assertThatThrownBy(() -> new Account(ID, " ", "TRY", BigDecimal.TEN))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Account(ID, "Owner", "try", BigDecimal.TEN))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Account(ID, "Owner", "TRYY", BigDecimal.TEN))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Account(ID, "Owner", "TRY", new BigDecimal("-0.01")))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Account(ID, "Owner", "TRY", new BigDecimal("1.234")))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void userCredentialOwnsOnlyItsOwnAccount() {
        UserCredential credential = new UserCredential("demo1", new PasswordHash("hash"), ID);
        assertThat(credential.owns(new AccountId("acc-001"))).isTrue();
        assertThat(credential.owns(new AccountId("acc-002"))).isFalse();
    }

    @Test
    void userCredentialRejectsInvalidUsername() {
        PasswordHash hash = new PasswordHash("hash");
        assertThatThrownBy(() -> new UserCredential(" ", hash, ID)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new UserCredential("u".repeat(65), hash, ID))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void passwordHashRejectsBlankAndHidesItsValue() {
        assertThatThrownBy(() -> new PasswordHash(" ")).isInstanceOf(IllegalArgumentException.class);
        assertThat(new PasswordHash("secret-hash-value").toString()).doesNotContain("secret-hash-value");
    }

    @Test
    void verificationKeyRequiresPositiveNumbersAndKeyId() {
        assertThatThrownBy(() -> new VerificationKey(" ", BigInteger.ONE, BigInteger.ONE))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new VerificationKey("kid", BigInteger.ZERO, BigInteger.ONE))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new VerificationKey("kid", BigInteger.ONE, BigInteger.valueOf(-1)))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(new VerificationKey("kid", BigInteger.TEN, BigInteger.valueOf(3)).keyId()).isEqualTo("kid");
    }
}
