package com.quancrypt.qbank.account.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.account.domain.model.PasswordHash;
import com.quancrypt.qbank.account.infrastructure.security.BcryptPasswordVerifier;
import com.quancrypt.qbank.account.port.outbound.PasswordVerifier;
import com.quancrypt.qbank.account.support.FakePasswordVerifier;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

/** Every PasswordVerifier implementation must pass these tests (Liskov substitution). */
abstract class PasswordVerifierContractTest {

    abstract PasswordVerifier create();

    /** A hash that {@link #create()} accepts for exactly the given raw password. */
    abstract PasswordHash hashOf(String rawPassword);

    @Test
    void acceptsTheCorrectPassword() {
        assertThat(create().matches("correct horse", hashOf("correct horse"))).isTrue();
    }

    @Test
    void rejectsAWrongPassword() {
        assertThat(create().matches("wrong", hashOf("correct horse"))).isFalse();
    }

    @Test
    void rejectsAnEmptyPasswordAndNulls() {
        PasswordVerifier verifier = create();
        PasswordHash hash = hashOf("correct horse");

        assertThat(verifier.matches("", hash)).isFalse();
        assertThat(verifier.matches(null, hash)).isFalse();
        assertThat(verifier.matches("correct horse", null)).isFalse();
    }
}

class FakePasswordVerifierContractTest extends PasswordVerifierContractTest {

    @Override
    PasswordVerifier create() {
        return new FakePasswordVerifier();
    }

    @Override
    PasswordHash hashOf(String rawPassword) {
        return FakePasswordVerifier.hashOf(rawPassword);
    }
}

class BcryptPasswordVerifierContractTest extends PasswordVerifierContractTest {

    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder(4);

    @Override
    PasswordVerifier create() {
        return new BcryptPasswordVerifier();
    }

    @Override
    PasswordHash hashOf(String rawPassword) {
        return new PasswordHash(encoder.encode(rawPassword));
    }

    @Test
    void aMalformedHashNeverMatches() {
        assertThat(create().matches("anything", new PasswordHash("not-a-bcrypt-hash"))).isFalse();
    }
}
