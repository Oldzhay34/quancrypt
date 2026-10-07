package com.quancrypt.qbank.account.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.infrastructure.security.NimbusTokenIssuer;
import com.quancrypt.qbank.account.port.outbound.TokenIssuer;
import com.quancrypt.qbank.account.support.FakeTokenIssuer;
import com.quancrypt.qbank.account.support.TestData;
import com.quancrypt.qbank.account.support.TokenFactory;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** Every TokenIssuer implementation must pass these tests (Liskov substitution). */
abstract class TokenIssuerContractTest {

    abstract TokenIssuer create();

    @Test
    void issuesANonBlankTokenForAValidRequest() {
        assertThat(create().issue("demo1", TestData.NOW, Duration.ofMinutes(15))).isNotBlank();
    }

    @Test
    void rejectsABlankSubject() {
        TokenIssuer issuer = create();

        assertThatThrownBy(() -> issuer.issue(" ", TestData.NOW, Duration.ofMinutes(1)))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> issuer.issue(null, TestData.NOW, Duration.ofMinutes(1)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsANonPositiveLifetime() {
        TokenIssuer issuer = create();

        assertThatThrownBy(() -> issuer.issue("demo1", TestData.NOW, Duration.ZERO))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> issuer.issue("demo1", TestData.NOW, Duration.ofSeconds(-5)))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> issuer.issue("demo1", TestData.NOW, null))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsAMissingIssueTime() {
        assertThatThrownBy(() -> create().issue("demo1", null, Duration.ofMinutes(1)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

class FakeTokenIssuerContractTest extends TokenIssuerContractTest {

    @Override
    TokenIssuer create() {
        return new FakeTokenIssuer();
    }
}

class NimbusTokenIssuerContractTest extends TokenIssuerContractTest {

    @Override
    TokenIssuer create() {
        return new NimbusTokenIssuer(TokenFactory.realKeys());
    }
}
