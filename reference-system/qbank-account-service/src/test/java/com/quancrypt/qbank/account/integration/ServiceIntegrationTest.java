package com.quancrypt.qbank.account.integration;

import com.quancrypt.qbank.account.support.ServiceClient;
import com.quancrypt.qbank.account.support.TestCertificates;
import java.nio.file.Path;
import javax.net.ssl.SSLContext;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Starts the real service on a random port with the real demo certificates. All subclasses share one application
 * context. The test clients get their TLS identity from additional SSL bundles defined below.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
abstract class ServiceIntegrationTest {

    static final String LOGIN_BODY_DEMO1 = "{\"username\":\"demo1\",\"password\":\"demo1-demo-pass\"}";

    @Autowired
    private SslBundles sslBundles;

    @Autowired
    private Environment environment;

    @DynamicPropertySource
    static void certificates(DynamicPropertyRegistry registry) {
        Path dir = TestCertificates.dir();
        registry.add("qbank.certs-dir", dir::toString);
        registry.add("management.server.port", () -> "0");
        registerClientBundle(registry, "gwaccount", dir, "gateway-to-account");
        registerClientBundle(registry, "gwpayment", dir, "gateway-to-payment");
        registerClientBundle(registry, "payaccount", dir, "payment-to-account");
        // A server certificate (serverAuth only) presented as a client certificate.
        registerClientBundle(registry, "servercert", dir, "qbank-gateway");
        registry.add("spring.ssl.bundle.pem.nocert.truststore.certificate", () -> "file:" + dir.resolve("ca.crt.pem"));
    }

    private static void registerClientBundle(DynamicPropertyRegistry registry, String bundle, Path dir, String file) {
        String prefix = "spring.ssl.bundle.pem." + bundle;
        registry.add(prefix + ".keystore.certificate", () -> "file:" + dir.resolve(file + ".crt.pem"));
        registry.add(prefix + ".keystore.private-key", () -> "file:" + dir.resolve(file + ".key.pem"));
        registry.add(prefix + ".truststore.certificate", () -> "file:" + dir.resolve("ca.crt.pem"));
    }

    final int port() {
        return environment.getRequiredProperty("local.server.port", Integer.class);
    }

    final int managementPort() {
        return environment.getRequiredProperty("local.management.port", Integer.class);
    }

    final SSLContext sslContext(String bundle) {
        return sslBundles.getBundle(bundle).createSslContext();
    }

    /** A client that presents the gateway-to-account client certificate. */
    final ServiceClient gatewayClient() {
        return new ServiceClient(sslContext("gwaccount"), port());
    }

    final ServiceClient clientFor(String bundle) {
        return new ServiceClient(sslContext(bundle), port());
    }
}
