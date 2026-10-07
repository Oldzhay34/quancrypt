package com.quancrypt.qbank.payment.api.mqtt;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.networknt.schema.InputFormat;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import com.quancrypt.qbank.payment.facade.TerminalTransactionFacade;
import com.quancrypt.qbank.payment.support.Fakes.FakeTerminalTransactionRepository;
import com.quancrypt.qbank.payment.usecase.RecordTerminalTransactionService;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

/** The MQTT inbound adapter without a broker: parsing, schema, topic check, facade call, logging. */
class TerminalTransactionListenerTest {

    private static final String TOPIC = "terminal/terminal-001/transactions";
    private static final String VALID = message("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11", "terminal-001", "12.50", "TRY");

    private FakeTerminalTransactionRepository repository;
    private TerminalTransactionListener listener;

    @BeforeEach
    void setUp() throws IOException {
        repository = new FakeTerminalTransactionRepository();
        Path schemaFile = Path.of(System.getProperty("qbank.contracts.dir")).resolve("terminal-transaction.schema.json");
        Schema schema = SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12)
                .getSchema(Files.readString(schemaFile), InputFormat.JSON);
        listener = new TerminalTransactionListener(
                new TerminalTransactionFacade(new RecordTerminalTransactionService(repository)), schema);
    }

    private static String message(String id, String terminal, String amount, String currency) {
        return "{\"transactionId\":\"" + id + "\",\"terminalId\":\"" + terminal + "\",\"accountId\":\"acc-001\","
                + "\"amount\":\"" + amount + "\",\"currency\":\"" + currency + "\",\"occurredAt\":\"2026-10-07T10:15:30Z\"}";
    }

    private String process(String topic, String payload) {
        return listener.process(topic, payload == null ? null : payload.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void aValidMessageIsRecordedOnceAndARepeatIsADuplicate() {
        assertThat(process(TOPIC, VALID)).isEqualTo("recorded");
        assertThat(process(TOPIC, VALID)).isEqualTo("duplicate");
        assertThat(repository.findById(UUID.fromString("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11"))).isPresent();
    }

    @Test
    void theTerminalIdOfTheMessageMustEqualTheTerminalIdOfTheTopic() {
        assertThat(process("terminal/terminal-002/transactions", VALID)).isEqualTo("rejected:topic-mismatch");
        assertThat(repository.findById(UUID.fromString("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11"))).isEmpty();
    }

    @Test
    void topicsOutsideThePatternAreRejected() {
        for (String topic : new String[] {
            null, "", "terminal/transactions", "terminal/terminal-001/other", "other/terminal-001/transactions",
            "terminal//transactions", "terminal/terminal-001/transactions/extra"}) {
            assertThat(process(topic, VALID)).as("topic %s", topic).isEqualTo("rejected:invalid-topic");
        }
    }

    @Test
    void emptyAndOversizedPayloadsAreRejectedBeforeParsing() {
        assertThat(process(TOPIC, null)).isEqualTo("rejected:invalid-size");
        assertThat(process(TOPIC, "")).isEqualTo("rejected:invalid-size");
        assertThat(process(TOPIC, " ".repeat(TerminalTransactionListener.MAX_PAYLOAD_BYTES + 1)))
                .isEqualTo("rejected:invalid-size");
    }

    @Test
    void textThatIsNotJsonIsRejected() {
        assertThat(process(TOPIC, "not json at all")).isEqualTo("rejected:invalid-json");
        assertThat(process(TOPIC, "{\"transactionId\":")).isEqualTo("rejected:invalid-json");
    }

    @Test
    void messagesThatViolateTheContractSchemaAreRejected() {
        String extraField = VALID.replace("}", ",\"cardNumber\":\"4111111111111111\"}");
        String oneDecimal = message("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11", "terminal-001", "12.5", "TRY");
        String lowerCurrency = message("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11", "terminal-001", "12.50", "try");
        String missingField = VALID.replace("\"accountId\":\"acc-001\",", "");

        for (String bad : new String[] {extraField, oneDecimal, lowerCurrency, missingField, "[]", "\"text\"", "{}"}) {
            assertThat(process(TOPIC, bad)).as("message %s", bad).isEqualTo("rejected:schema-violation");
        }
        assertThat(repository.findById(UUID.fromString("3f2b8c1e-5d4a-4b7e-9c1d-2a6f0e8b7c11"))).isEmpty();
    }

    @Test
    void aTransactionIdThatIsNotAUuidIsNeverRecorded() {
        String outcome = process(TOPIC, message("not-a-uuid", "terminal-001", "12.50", "TRY"));

        assertThat(outcome).isIn("rejected:schema-violation", "rejected:invalid-fields");
    }

    @Test
    void theListenerLogsOnlyTheOutcomeNeverTheMessageContent() {
        Logger logger = (Logger) LoggerFactory.getLogger(TerminalTransactionListener.class);
        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            listener.messageArrived(TOPIC, new MqttMessage(VALID.getBytes(StandardCharsets.UTF_8)));
            listener.messageArrived(TOPIC, new MqttMessage("secret garbage 4111111111111111".getBytes(StandardCharsets.UTF_8)));
        } finally {
            logger.detachAppender(appender);
        }

        assertThat(appender.list).extracting(ILoggingEvent::getFormattedMessage)
                .containsExactly("terminal message recorded", "terminal message rejected:invalid-json");
    }

    @Test
    void messageArrivedNeverThrows() {
        listener.messageArrived(null, new MqttMessage(new byte[0]));
        listener.messageArrived(TOPIC, new MqttMessage());
    }
}
