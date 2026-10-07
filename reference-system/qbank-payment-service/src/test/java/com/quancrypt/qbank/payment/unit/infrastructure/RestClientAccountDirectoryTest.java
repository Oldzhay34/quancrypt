package com.quancrypt.qbank.payment.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.payment.domain.model.AccountId;
import com.quancrypt.qbank.payment.domain.model.AccountSummary;
import com.quancrypt.qbank.payment.domain.model.Caller;
import com.quancrypt.qbank.payment.infrastructure.client.RestClientAccountDirectory;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException;
import com.quancrypt.qbank.payment.port.outbound.AccountLookupException.Reason;
import com.quancrypt.qbank.payment.support.AccountServiceStub;
import com.quancrypt.qbank.payment.support.PemSsl;
import com.quancrypt.qbank.payment.support.TokenFactory;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import java.net.http.HttpClient;
import java.time.Duration;
import javax.net.ssl.SSLContext;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/** The account directory adapter against the HTTPS test double: mTLS identity, token forwarding, failure handling. */
class RestClientAccountDirectoryTest {

    private static AccountServiceStub stub;
    private static final TokenFactory TOKENS = new TokenFactory();

    @BeforeAll
    static void startStub() {
        stub = new AccountServiceStub();
    }

    @AfterAll
    static void stopStub() {
        stub.close();
    }

    private static RestClientAccountDirectory directory(SSLContext ssl, int port, int readTimeoutMs, CircuitBreaker breaker) {
        HttpClient http = HttpClient.newBuilder().sslContext(ssl).connectTimeout(Duration.ofMillis(500)).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(http);
        factory.setReadTimeout(Duration.ofMillis(readTimeoutMs));
        RestClient client = RestClient.builder().baseUrl("https://localhost:" + port).requestFactory(factory).build();
        Retry retry = Retry.of("test", RetryConfig.custom().maxAttempts(2).waitDuration(Duration.ofMillis(10))
                .retryExceptions(RestClientAccountDirectory.TransientUpstreamException.class).build());
        return new RestClientAccountDirectory(client, breaker, retry);
    }

    private static CircuitBreaker breaker(int window) {
        return CircuitBreaker.of("test", CircuitBreakerConfig.custom()
                .slidingWindowSize(window).minimumNumberOfCalls(window).failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .recordExceptions(RestClientAccountDirectory.TransientUpstreamException.class)
                .ignoreExceptions(AccountLookupException.class).build());
    }

    private static RestClientAccountDirectory directory() {
        return directory(PemSsl.withIdentity("payment-to-account.crt.pem", "payment-to-account.key.pem"),
                stub.port(), 3000, breaker(10));
    }

    private static Caller demo1() {
        return new Caller("demo1", TOKENS.valid("demo1"));
    }

    private static Reason reasonOf(RestClientAccountDirectory directory, String accountId, Caller caller) {
        try {
            directory.findAccount(new AccountId(accountId), caller);
        } catch (AccountLookupException e) {
            return e.reason();
        }
        throw new AssertionError("expected a failure for " + accountId);
    }

    @Test
    void anOwnedAccountIsReturnedWithTheCallersTokenAndTheClientCertificateIdentity() {
        Caller caller = demo1();
        long before = stub.receivedFor("/api/v1/accounts/acc-001");

        AccountSummary summary = directory().findAccount(new AccountId("acc-001"), caller);

        assertThat(summary.accountId().value()).isEqualTo("acc-001");
        assertThat(summary.currency()).isEqualTo("TRY");
        AccountServiceStub.Received last = stub.received().get(stub.received().size() - 1);
        assertThat(last.path()).isEqualTo("/api/v1/accounts/acc-001");
        assertThat(last.authorization()).isEqualTo("Bearer " + caller.bearerToken());
        assertThat(last.clientCertificateSubject()).contains("CN=payment-to-account");
        assertThat(stub.receivedFor("/api/v1/accounts/acc-001")).isEqualTo(before + 1);
    }

    @Test
    void theTraceIdOfTheCurrentRequestIsForwarded() {
        MDC.put("traceId", "trace-from-test");
        try {
            directory().findAccount(new AccountId("acc-001"), demo1());
        } finally {
            MDC.remove("traceId");
        }

        assertThat(stub.received().get(stub.received().size() - 1).traceId()).isEqualTo("trace-from-test");
    }

    @Test
    void businessAnswersMapToReasonsAndAreNotRetried() {
        RestClientAccountDirectory directory = directory();
        long notFoundBefore = stub.receivedFor("/api/v1/accounts/acc-999");

        assertThat(reasonOf(directory, "acc-999", demo1())).isEqualTo(Reason.NOT_FOUND);
        assertThat(reasonOf(directory, "acc-002", demo1())).isEqualTo(Reason.FORBIDDEN);
        assertThat(reasonOf(directory, "acc-001", new Caller("demo1", "not-a-jwt"))).isEqualTo(Reason.UNAUTHORIZED);
        assertThat(stub.receivedFor("/api/v1/accounts/acc-999")).isEqualTo(notFoundBefore + 1);
    }

    @Test
    void aServerErrorIsRetriedOnceAndThenReportedAsUnavailable() {
        long before = stub.receivedFor("/api/v1/accounts/acc-500");

        assertThat(reasonOf(directory(), "acc-500", demo1())).isEqualTo(Reason.UNAVAILABLE);
        assertThat(stub.receivedFor("/api/v1/accounts/acc-500")).isEqualTo(before + 2);
    }

    @Test
    void aRefusedRequestIsUnavailableButNeitherRetriedNorCountedAgainstTheCircuitBreaker() {
        RestClientAccountDirectory directory = directory(
                PemSsl.withIdentity("payment-to-account.crt.pem", "payment-to-account.key.pem"),
                stub.port(), 3000, breaker(4));
        long before = stub.receivedFor("/api/v1/accounts/acc-400");

        for (int i = 0; i < 6; i++) {
            assertThat(reasonOf(directory, "acc-400", demo1())).isEqualTo(Reason.UNAVAILABLE);
        }

        assertThat(stub.receivedFor("/api/v1/accounts/acc-400")).as("one attempt per lookup").isEqualTo(before + 6);
        assertThat(directory.findAccount(new AccountId("acc-001"), demo1()).accountId().value())
                .as("the circuit stays closed").isEqualTo("acc-001");
    }

    @Test
    void aFailureThatGoesAwayOnTheRetryStillSucceeds() {
        AccountSummary summary = directory().findAccount(new AccountId("acc-flaky"), demo1());

        assertThat(summary.accountId().value()).isEqualTo("acc-flaky");
        assertThat(stub.receivedFor("/api/v1/accounts/acc-flaky")).isEqualTo(2);
    }

    @Test
    void aSlowAnswerHitsTheReadTimeout() {
        RestClientAccountDirectory directory = directory(
                PemSsl.withIdentity("payment-to-account.crt.pem", "payment-to-account.key.pem"),
                stub.port(), 300, breaker(10));

        assertThat(reasonOf(directory, "acc-slow", demo1())).isEqualTo(Reason.UNAVAILABLE);
    }

    @Test
    void aServiceThatIsNotListeningIsUnavailable() {
        int closedPort;
        try (AccountServiceStub other = new AccountServiceStub()) {
            closedPort = other.port();
        }
        RestClientAccountDirectory directory = directory(
                PemSsl.withIdentity("payment-to-account.crt.pem", "payment-to-account.key.pem"),
                closedPort, 500, breaker(10));

        assertThat(reasonOf(directory, "acc-001", demo1())).isEqualTo(Reason.UNAVAILABLE);
    }

    @Test
    void withoutAClientCertificateTheTlsHandshakeFailsAndNoRequestReachesTheService() {
        long before = stub.received().size();
        RestClientAccountDirectory directory = directory(PemSsl.trustOnly(), stub.port(), 1000, breaker(10));

        assertThat(reasonOf(directory, "acc-001", demo1())).isEqualTo(Reason.UNAVAILABLE);
        assertThat(stub.received().size()).isEqualTo(before);
    }

    @Test
    void theCircuitBreakerOpensAfterRepeatedFailuresAndStopsCallingTheService() {
        RestClientAccountDirectory directory = directory(
                PemSsl.withIdentity("payment-to-account.crt.pem", "payment-to-account.key.pem"),
                stub.port(), 3000, breaker(4));
        long before = stub.receivedFor("/api/v1/accounts/acc-500");

        // each lookup makes two recorded attempts; the window of four calls fills after two lookups
        assertThat(reasonOf(directory, "acc-500", demo1())).isEqualTo(Reason.UNAVAILABLE);
        assertThat(reasonOf(directory, "acc-500", demo1())).isEqualTo(Reason.UNAVAILABLE);
        long afterTwo = stub.receivedFor("/api/v1/accounts/acc-500");
        long healthyBefore = stub.receivedFor("/api/v1/accounts/acc-001");

        assertThat(reasonOf(directory, "acc-001", demo1())).isEqualTo(Reason.UNAVAILABLE);

        assertThat(afterTwo).isEqualTo(before + 4);
        assertThat(stub.receivedFor("/api/v1/accounts/acc-001"))
                .as("the open circuit refuses the call before it reaches the service").isEqualTo(healthyBefore);
    }
}
