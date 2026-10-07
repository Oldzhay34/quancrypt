package com.quancrypt.qbank.payment.api.mqtt;

import com.networknt.schema.Schema;
import com.quancrypt.qbank.payment.facade.TerminalTransactionFacade;
import com.quancrypt.qbank.payment.facade.dto.TerminalTransactionView;
import com.quancrypt.qbank.payment.facade.error.BadRequestException;
import java.util.Objects;
import org.eclipse.paho.client.mqttv3.IMqttMessageListener;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Inbound adapter for the topic terminal/{terminalId}/transactions: parses the message, validates it against the
 * contract's JSON Schema, checks that the terminal id in the message equals the one in the topic and hands the
 * transaction to the facade. A rejected message is dropped and only the reason is logged, never the content (D-103).
 * The listener never throws: an exception out of a Paho callback would drop the connection.
 */
public final class TerminalTransactionListener implements IMqttMessageListener {

    static final int MAX_PAYLOAD_BYTES = 4096;
    private static final Logger LOG = LoggerFactory.getLogger(TerminalTransactionListener.class);
    private static final String[] TOPIC_PARTS = {"terminal", null, "transactions"};

    private final TerminalTransactionFacade facade;
    private final Schema schema;
    private final JsonMapper json = JsonMapper.builder().build();

    public TerminalTransactionListener(TerminalTransactionFacade facade, Schema schema) {
        this.facade = Objects.requireNonNull(facade, "facade");
        this.schema = Objects.requireNonNull(schema, "schema");
    }

    @Override
    public void messageArrived(String topic, MqttMessage message) {
        String outcome;
        try {
            outcome = process(topic, message.getPayload());
        } catch (RuntimeException e) {
            outcome = "rejected:error";
        }
        LOG.info("terminal message {}", outcome);
    }

    /** Processes one message and returns "recorded", "duplicate" or "rejected:&lt;reason&gt;". */
    String process(String topic, byte[] payload) {
        String topicTerminalId = terminalIdOf(topic);
        if (topicTerminalId == null) {
            return "rejected:invalid-topic";
        }
        if (payload == null || payload.length == 0 || payload.length > MAX_PAYLOAD_BYTES) {
            return "rejected:invalid-size";
        }
        JsonNode node;
        try {
            node = json.readTree(payload);
        } catch (RuntimeException e) {
            return "rejected:invalid-json";
        }
        if (!schema.validate(node).isEmpty()) {
            return "rejected:schema-violation";
        }
        if (!topicTerminalId.equals(node.get("terminalId").asString())) {
            return "rejected:topic-mismatch";
        }
        try {
            boolean recorded = facade.record(new TerminalTransactionView(
                    node.get("transactionId").asString(),
                    node.get("terminalId").asString(),
                    node.get("accountId").asString(),
                    node.get("amount").asString(),
                    node.get("currency").asString(),
                    node.get("occurredAt").asString()));
            return recorded ? "recorded" : "duplicate";
        } catch (BadRequestException e) {
            return "rejected:invalid-fields";
        }
    }

    private static String terminalIdOf(String topic) {
        if (topic == null) {
            return null;
        }
        String[] parts = topic.split("/", -1);
        if (parts.length != TOPIC_PARTS.length || !TOPIC_PARTS[0].equals(parts[0])
                || !TOPIC_PARTS[2].equals(parts[2]) || parts[1].isEmpty()) {
            return null;
        }
        return parts[1];
    }
}
