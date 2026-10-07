package com.quancrypt.qbank.payment.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.AccountSummary;
import com.quancrypt.qbank.payment.domain.model.Caller;
import com.quancrypt.qbank.payment.infrastructure.client.RestClientAccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException.Reason;
import com.quancrypt.qbank.payment.support.AccountServiceStub;
import com.quancrypt.qbank.payment.support.Fakes.FakeAccountDirectory;
import com.quancrypt.qbank.payment.support.PemSsl;
import com.quancrypt.qbank.payment.support.TokenFactory;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import java.net.http.HttpClient;
import java.time.Duration;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/**
 * Contract of AccountDirectory (Liskov substitution). The account ids mean the same to every implementation:
 * acc-001 belongs to the caller demo1, acc-002 to somebody else, acc-999 does not exist.
 */
abstract class AccountDirectoryContractTest {

    private static final Caller DEMO1 = new Caller("demo1", new TokenFactory().valid("demo1"));

    abstract AccountDirectory create();

    @Test
    void returnsTheAccountTheCallerOwns() {
        AccountSummary summary = create().findAccount(new AccountId("acc-001"), DEMO1);

        assertThat(summary.accountId()).isEqualTo(new AccountId("acc-001"));
        assertThat(summary.currency()).isEqualTo("TRY");
    }

    @Test
    void reportsAnAccountOfSomebodyElseAsForbidden() {
        assertThatThrownBy(() -> create().findAccount(new AccountId("acc-002"), DEMO1))
                .isInstanceOfSatisfying(AccountLookupException.class, e -> assertThat(e.reason()).isEqualTo(Reason.FORBIDDEN));
    }

    @Test
    void reportsAnUnknownAccountAsNotFound() {
        assertThatThrownBy(() -> create().findAccount(new AccountId("acc-999"), DEMO1))
                .isInstanceOfSatisfying(AccountLookupException.class, e -> assertThat(e.reason()).isEqualTo(Reason.NOT_FOUND));
    }
}

class FakeAccountDirectoryContractTest extends AccountDirectoryContractTest {

    @Override
    AccountDirectory create() {
        return new FakeAccountDirectory().failFor("acc-002", Reason.FORBIDDEN).failFor("acc-999", Reason.NOT_FOUND);
    }
}

class RestClientAccountDirectoryContractTest extends AccountDirectoryContractTest {

    private static final AccountServiceStub STUB = new AccountServiceStub();

    @AfterAll
    static void stopStub() {
        STUB.close();
    }

    @Override
    AccountDirectory create() {
        HttpClient http = HttpClient.newBuilder()
                .sslContext(PemSsl.withIdentity("payment-to-account.crt.pem", "payment-to-account.key.pem"))
                .connectTimeout(Duration.ofSeconds(2)).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(Duration.ofSeconds(3));
        RestClient client = RestClient.builder().baseUrl(STUB.baseUrl()).requestFactory(factory).build();
        Retry retry = Retry.of("contract", RetryConfig.custom().maxAttempts(2).waitDuration(Duration.ofMillis(10))
                .retryExceptions(RestClientAccountDirectory.TransientUpstreamException.class).build());
        return new RestClientAccountDirectory(client, CircuitBreaker.ofDefaults("contract"), retry);
    }
}
