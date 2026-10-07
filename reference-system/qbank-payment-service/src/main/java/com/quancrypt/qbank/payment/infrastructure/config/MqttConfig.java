package com.quancrypt.qbank.payment.infrastructure.config;

import com.networknt.schema.InputFormat;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import com.quancrypt.qbank.payment.api.mqtt.TerminalTransactionListener;
import com.quancrypt.qbank.payment.facade.TerminalTransactionFacade;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

/**
 * The MQTT subscription for terminal transactions: the contract's JSON Schema, the listener (an inbound adapter in
 * the api layer) and the Paho connection with its TLS client identity (SSL bundle "mqttclient").
 */
@Configuration
public class MqttConfig {

    private static final String SCHEMA_RESOURCE = "contracts/terminal-transaction.schema.json";
    private static final int KEEP_ALIVE_SECONDS = 30;
    private static final int CONNECTION_TIMEOUT_SECONDS = 10;
    private static final int MAX_RECONNECT_DELAY_MS = 30_000;

    @Bean
    Schema terminalTransactionSchema() throws IOException {
        try (InputStream in = new ClassPathResource(SCHEMA_RESOURCE).getInputStream()) {
            String schema = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            return SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12)
                    .getSchema(schema, InputFormat.JSON);
        }
    }

    @Bean
    TerminalTransactionListener terminalTransactionListener(TerminalTransactionFacade facade, Schema schema) {
        return new TerminalTransactionListener(facade, schema);
    }

    @Bean
    MqttSubscriptionLifecycle mqttSubscriptionLifecycle(
            QbankProperties properties, SslBundles sslBundles, TerminalTransactionListener listener) throws MqttException {
        QbankProperties.Mqtt mqtt = properties.mqtt();
        MqttClient client = new MqttClient(mqtt.brokerUrl(), mqtt.clientId(), new MemoryPersistence());
        MqttConnectOptions options = new MqttConnectOptions();
        options.setMqttVersion(MqttConnectOptions.MQTT_VERSION_3_1_1);
        options.setSocketFactory(sslBundles.getBundle("mqttclient").createSslContext().getSocketFactory());
        options.setHttpsHostnameVerificationEnabled(true);
        options.setCleanSession(false);
        options.setAutomaticReconnect(true);
        options.setMaxReconnectDelay(MAX_RECONNECT_DELAY_MS);
        options.setKeepAliveInterval(KEEP_ALIVE_SECONDS);
        options.setConnectionTimeout(CONNECTION_TIMEOUT_SECONDS);
        return new MqttSubscriptionLifecycle(client, options, mqtt.topicFilter(), mqtt.qos(), listener, mqtt.retrySeconds());
    }
}
