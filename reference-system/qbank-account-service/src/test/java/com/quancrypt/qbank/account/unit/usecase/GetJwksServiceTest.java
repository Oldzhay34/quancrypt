package com.quancrypt.qbank.account.unit.usecase;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.port.inbound.JwksResult;
import com.quancrypt.qbank.account.support.FakeVerificationKeySource;
import com.quancrypt.qbank.account.usecase.GetJwksService;
import org.junit.jupiter.api.Test;

class GetJwksServiceTest {

    @Test
    void publishesEveryVerificationKey() {
        JwksResult result = new GetJwksService(new FakeVerificationKeySource()).getJwks();

        assertThat(result.keys()).containsExactly(new JwksResult.Key(
                FakeVerificationKeySource.KEY.keyId(),
                FakeVerificationKeySource.KEY.modulus(),
                FakeVerificationKeySource.KEY.exponent()));
    }

    @Test
    void requiresAKeySource() {
        assertThatThrownBy(() -> new GetJwksService(null)).isInstanceOf(NullPointerException.class);
    }
}
