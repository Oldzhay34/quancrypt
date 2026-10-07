package com.quancrypt.qbank.gateway.integration;

import com.quancrypt.qbank.gateway.support.BackendStub;
import com.quancrypt.qbank.gateway.support.PemSsl;
import com.quancrypt.qbank.gateway.support.ServiceClient;
import com.quancrypt.qbank.gateway.support.TestCertificates;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Starts the real gateway on a random port with the real demo certificates. The two back ends are test doubles with
 * the real service certificates that demand a client certificate. All subclasses share one application context.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
abstract class GatewayIntegrationTest {

    static final BackendStub ACCOUNT = new BackendStub("account", "qbank-account-service");
    static final BackendStub PAYMENT = new BackendStub("payment", "qbank-payment-service");

    static {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            ACCOUNT.close();
            PAYMENT.close();
        }));
    }

    @Autowired
    private Environment environment;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("qbank.certs-dir", () -> TestCertificates.dir().toString());
        registry.add("qbank.backends.account-url", ACCOUNT::baseUrl);
        registry.add("qbank.backends.payment-url", PAYMENT::baseUrl);
        registry.add("management.server.port", () -> "0");
    }

    final int port() {
        return environment.getRequiredProperty("local.server.port", Integer.class);
    }

    final int managementPort() {
        return environment.getRequiredProperty("local.management.port", Integer.class);
    }

    /** An external client: trusts the demo CA and presents no certificate. */
    final ServiceClient externalClient() {
        return new ServiceClient(PemSsl.trustOnly(), port());
    }
}
