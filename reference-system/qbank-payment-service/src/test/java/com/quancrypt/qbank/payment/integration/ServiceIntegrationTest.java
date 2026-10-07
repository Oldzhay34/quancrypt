package com.quancrypt.qbank.payment.integration;

import com.quancrypt.qbank.payment.support.AccountServiceStub;
import com.quancrypt.qbank.payment.support.PemSsl;
import com.quancrypt.qbank.payment.support.ServiceClient;
import com.quancrypt.qbank.payment.support.TestCertificates;
import java.nio.file.Path;
import javax.net.ssl.SSLContext;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Starts the real payment service on a random port with the real demo certificates and the account service test
 * double. All subclasses share one application context and one stub. The MQTT broker is deliberately unreachable
 * here (the MQTT integration test has its own context), which also shows that the service starts without a broker.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
abstract class ServiceIntegrationTest {

    static final AccountServiceStub ACCOUNT_SERVICE = new AccountServiceStub();

    static {
        Runtime.getRuntime().addShutdownHook(new Thread(ACCOUNT_SERVICE::close));
    }

    @Autowired
    private Environment environment;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        Path dir = TestCertificates.dir();
        registry.add("qbank.certs-dir", dir::toString);
        registry.add("qbank.account-service-url", ACCOUNT_SERVICE::baseUrl);
        registry.add("qbank.account-client.read-timeout-ms", () -> "700");
        registry.add("qbank.mqtt.broker-url", () -> "ssl://localhost:1");
        registry.add("management.server.port", () -> "0");
    }

    final int port() {
        return environment.getRequiredProperty("local.server.port", Integer.class);
    }

    final int managementPort() {
        return environment.getRequiredProperty("local.management.port", Integer.class);
    }

    /** A client presenting the gateway's client certificate (gateway-to-account serves both back ends, D-109). */
    final ServiceClient gatewayClient() {
        return new ServiceClient(PemSsl.withIdentity("gateway-to-account.crt.pem", "gateway-to-account.key.pem"), port());
    }

    final ServiceClient clientWithoutCertificate() {
        return new ServiceClient(PemSsl.trustOnly(), port());
    }

    /** A server certificate (serverAuth only) presented as a client certificate. */
    final ServiceClient clientWithServerCertificate() {
        return new ServiceClient(PemSsl.withIdentity("qbank-gateway.crt.pem", "qbank-gateway.key.pem"), port());
    }

    final SSLContext gatewaySslContext() {
        return PemSsl.withIdentity("gateway-to-account.crt.pem", "gateway-to-account.key.pem");
    }
}
