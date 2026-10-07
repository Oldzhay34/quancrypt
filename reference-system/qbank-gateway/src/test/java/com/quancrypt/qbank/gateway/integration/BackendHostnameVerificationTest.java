package com.quancrypt.qbank.gateway.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.gateway.support.BackendStub;
import com.quancrypt.qbank.gateway.support.PemSsl;
import com.quancrypt.qbank.gateway.support.ServiceClient;
import com.quancrypt.qbank.gateway.support.TestCertificates;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * The gateway must check the host name of the back end certificate. The route here points at 127.0.0.1, which is not
 * in the subject alternative names of the account service certificate (qbank-account-service, localhost).
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BackendHostnameVerificationTest {

    private static final BackendStub ACCOUNT = new BackendStub("account", "qbank-account-service");

    @Autowired
    private Environment environment;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("qbank.certs-dir", () -> TestCertificates.dir().toString());
        registry.add("qbank.backends.account-url", () -> "https://127.0.0.1:" + ACCOUNT.port());
        registry.add("qbank.backends.payment-url", () -> "https://localhost:1");
        registry.add("management.server.port", () -> "0");
    }

    @AfterAll
    static void stop() {
        ACCOUNT.close();
    }

    @Test
    void aBackEndWhoseCertificateDoesNotMatchTheHostIsNotReached() throws Exception {
        int port = environment.getRequiredProperty("local.server.port", Integer.class);

        ServiceClient.Response response = new ServiceClient(PemSsl.trustOnly(), port).get("/api/v1/accounts/acc-001", "token");

        assertThat(response.status()).isGreaterThanOrEqualTo(500);
        assertThat(ACCOUNT.received()).as("no request may reach a back end whose name does not match").isEmpty();
    }
}
