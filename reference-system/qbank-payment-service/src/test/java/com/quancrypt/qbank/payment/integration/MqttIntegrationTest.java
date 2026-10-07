package com.quancrypt.qbank.payment.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.domain.model.TerminalTransaction;
import com.quancrypt.qbank.payment.port.outbound.TerminalTransactionRepository;
import com.quancrypt.qbank.payment.support.AccountServiceStub;
import com.quancrypt.qbank.payment.support.PemSsl;
import com.quancrypt.qbank.payment.support.TestCertificates;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.UUID;
import javax.net.ssl.SSLContext;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

/**
 * The MQTT adapter against a real Mosquitto broker (eclipse-mosquitto:2.0.22 in a Testcontainers container): TLS is
 * required, the broker demands a client certificate, and the service subscribes with its own client identity.
 * Docker Desktop must be running (WSL integration enabled); without Docker this test fails, it is never skipped.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MqttIntegrationTest {

    private static final String IMAGE = "eclipse-mosquitto:2.0.22";
    private static final int BROKER_PORT = 8883;
    private static final String TOPIC = "terminal/terminal-001/transactions";
    private static final AccountServiceStub ACCOUNT_SERVICE = new AccountServiceStub();
    private static final GenericContainer<?> MOSQUITTO = startBroker();

    @Autowired
    private TerminalTransactionRepository transactions;

    private static GenericContainer<?> startBroker() {
        Path certs = TestCertificates.dir();
        GenericContainer<?> broker = new GenericContainer<>(DockerImageName.parse(IMAGE))
                .withExposedPorts(BROKER_PORT)
                .withCopyFileToContainer(
                        MountableFile.forClasspathResource("mosquitto/mosquitto.conf"), "/mosquitto/config/mosquitto.conf")
                .withCopyFileToContainer(MountableFile.forHostPath(certs.resolve("ca.crt.pem"), 0644), "/mosquitto/certs/ca.crt.pem")
                .withCopyFileToContainer(
                        MountableFile.forHostPath(certs.resolve("mosquitto.crt.pem"), 0644), "/mosquitto/certs/mosquitto.crt.pem")
                .withCopyFileToContainer(
                        MountableFile.forHostPath(certs.resolve("mosquitto.key.pem"), 0644), "/mosquitto/certs/mosquitto.key.pem")
                .waitingFor(Wait.forLogMessage(".*mosquitto version 2\\.0\\.22 running.*", 1));
        try {
            broker.start();
        } catch (RuntimeException e) {
            throw new IllegalStateException(
                    "the Mosquitto test container could not start: Docker Desktop must be running with WSL integration", e);
        }
        return broker;
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("qbank.certs-dir", () -> TestCertificates.dir().toString());
        registry.add("qbank.account-service-url", ACCOUNT_SERVICE::baseUrl);
        registry.add("qbank.mqtt.broker-url", () -> "ssl://localhost:" + MOSQUITTO.getMappedPort(BROKER_PORT));
        registry.add("qbank.mqtt.retry-seconds", () -> "1");
        registry.add("management.server.port", () -> "0");
    }

    @AfterAll
    static void stopBroker() {
        MOSQUITTO.stop();
        ACCOUNT_SERVICE.close();
    }

    private static String brokerUrl() {
        return "ssl://localhost:" + MOSQUITTO.getMappedPort(BROKER_PORT);
    }

    private static String message(UUID id, String terminalId, String amount) {
        return "{\"transactionId\":\"" + id + "\",\"terminalId\":\"" + terminalId + "\",\"accountId\":\"acc-001\","
                + "\"amount\":\"" + amount + "\",\"currency\":\"TRY\",\"occurredAt\":\"2026-10-07T10:15:30Z\"}";
    }

    private static MqttClient connect(SSLContext ssl, String clientId) throws MqttException {
        MqttClient client = new MqttClient(brokerUrl(), clientId, new MemoryPersistence());
        MqttConnectOptions options = new MqttConnectOptions();
        options.setSocketFactory(ssl.getSocketFactory());
        options.setCleanSession(true);
        options.setConnectionTimeout(10);
        client.connect(options);
        return client;
    }

    private static void publish(String topic, String payload) throws MqttException {
        MqttClient terminal = connect(
                PemSsl.withIdentity("terminal-001.crt.pem", "terminal-001.key.pem"), "terminal-001-" + UUID.randomUUID());
        try {
            terminal.publish(topic, payload.getBytes(StandardCharsets.UTF_8), 1, false);
        } finally {
            terminal.disconnect();
            terminal.close();
        }
    }

    /** Publishes the message every half second until the service has recorded it (the subscription may still be starting). */
    private TerminalTransaction publishUntilRecorded(UUID id, String payload) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(40).toNanos();
        while (System.nanoTime() < deadline) {
            publish(TOPIC, payload);
            for (int i = 0; i < 5; i++) {
                var found = transactions.findById(id);
                if (found.isPresent()) {
                    return found.get();
                }
                Thread.sleep(100);
            }
        }
        throw new AssertionError("the transaction " + id + " was not recorded within 40 seconds");
    }

    @Test
    void aTransactionPublishedOverTlsWithTheTerminalCertificateIsRecorded() throws Exception {
        UUID id = UUID.fromString("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11");

        TerminalTransaction recorded = publishUntilRecorded(id, message(id, "terminal-001", "12.50"));

        assertThat(recorded.terminalId()).isEqualTo("terminal-001");
        assertThat(recorded.accountId().value()).isEqualTo("acc-001");
        assertThat(recorded.amount().toPlainString()).isEqualTo("12.50");
        assertThat(recorded.currency()).isEqualTo("TRY");
        assertThat(recorded.occurredAt().toString()).isEqualTo("2026-10-07T10:15:30Z");
    }

    @Test
    void rejectedMessagesAreDroppedAndARepeatedTransactionIdKeepsTheFirstRecord() throws Exception {
        UUID ready = UUID.randomUUID();
        publishUntilRecorded(ready, message(ready, "terminal-001", "1.00"));
        UUID withCardData = UUID.randomUUID();
        UUID wrongTopic = UUID.randomUUID();
        UUID repeated = UUID.randomUUID();
        UUID last = UUID.randomUUID();

        publish(TOPIC, "this is not json");
        publish(TOPIC, message(withCardData, "terminal-001", "2.00").replace("}", ",\"cardNumber\":\"4111111111111111\"}"));
        publish("terminal/terminal-002/transactions", message(wrongTopic, "terminal-001", "3.00"));
        publish(TOPIC, message(repeated, "terminal-001", "4.00"));
        publish(TOPIC, message(repeated, "terminal-001", "99.00"));
        publish(TOPIC, message(last, "terminal-001", "5.00"));
        TerminalTransaction lastRecorded = publishUntilRecorded(last, message(last, "terminal-001", "5.00"));

        assertThat(lastRecorded.amount().toPlainString()).isEqualTo("5.00");
        assertThat(transactions.findById(withCardData)).as("schema violation").isEmpty();
        assertThat(transactions.findById(wrongTopic)).as("terminal id differs from the topic").isEmpty();
        assertThat(transactions.findById(repeated).orElseThrow().amount().toPlainString()).isEqualTo("4.00");
    }

    @Test
    void aClientWithoutACertificateCannotEvenConnectToTheBroker() {
        assertThatThrownBy(() -> connect(PemSsl.trustOnly(), "no-certificate-" + UUID.randomUUID()))
                .isInstanceOf(MqttException.class);
    }

    @Test
    void theBrokerAcceptsTheServiceClientIdentityAndTheTerminalIdentity() throws Exception {
        for (String[] identity : new String[][] {
            {"payment-to-mosquitto.crt.pem", "payment-to-mosquitto.key.pem"},
            {"terminal-001.crt.pem", "terminal-001.key.pem"}}) {
            MqttClient client = connect(PemSsl.withIdentity(identity[0], identity[1]), "identity-" + UUID.randomUUID());
            try {
                assertThat(client.isConnected()).isTrue();
            } finally {
                client.disconnect();
                client.close();
            }
        }
    }
}
