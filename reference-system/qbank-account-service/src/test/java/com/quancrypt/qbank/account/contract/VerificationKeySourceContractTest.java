package com.quancrypt.qbank.account.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.account.domain.model.VerificationKey;
import com.quancrypt.qbank.account.infrastructure.security.RsaVerificationKeySource;
import com.quancrypt.qbank.account.port.outbound.VerificationKeySource;
import com.quancrypt.qbank.account.support.FakeVerificationKeySource;
import com.quancrypt.qbank.account.support.TokenFactory;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Every VerificationKeySource implementation must pass these tests (Liskov substitution). */
abstract class VerificationKeySourceContractTest {

    abstract VerificationKeySource create();

    @Test
    void returnsAtLeastOneKey() {
        assertThat(create().verificationKeys()).isNotEmpty();
    }

    @Test
    void everyKeyHasAnIdAndPositiveNumbers() {
        for (VerificationKey key : create().verificationKeys()) {
            assertThat(key.keyId()).isNotBlank();
            assertThat(key.modulus().signum()).isPositive();
            assertThat(key.exponent().signum()).isPositive();
        }
    }

    @Test
    void keyIdsAreUnique() {
        List<String> ids = create().verificationKeys().stream().map(VerificationKey::keyId).toList();

        assertThat(ids).doesNotHaveDuplicates();
    }
}

class FakeVerificationKeySourceContractTest extends VerificationKeySourceContractTest {

    @Override
    VerificationKeySource create() {
        return new FakeVerificationKeySource();
    }
}

class RsaVerificationKeySourceContractTest extends VerificationKeySourceContractTest {

    @Override
    VerificationKeySource create() {
        return new RsaVerificationKeySource(TokenFactory.realKeys());
    }

    @Test
    void publishesTheModulusOfTheSigningKey() {
        var keys = TokenFactory.realKeys();

        assertThat(new RsaVerificationKeySource(keys).verificationKeys().get(0).modulus())
                .isEqualTo(keys.publicKey().getModulus());
    }
}
