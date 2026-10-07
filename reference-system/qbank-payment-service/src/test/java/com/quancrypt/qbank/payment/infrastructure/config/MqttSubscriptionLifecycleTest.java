package com.quancrypt.qbank.payment.infrastructure.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import com.quancrypt.qbank.payment.support.PemSsl;
import org.eclipse.paho.client.mqttv3.IMqttMessageListener;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.junit.jupiter.api.Test;

/** The subscription lifecycle without a broker: it must survive stop and start, as Spring pauses and resumes contexts. */
class MqttSubscriptionLifecycleTest {

    private static MqttSubscriptionLifecycle lifecycle() throws MqttException {
        MqttClient client = new MqttClient("ssl://localhost:1", "lifecycle-test", new MemoryPersistence());
        MqttConnectOptions options = new MqttConnectOptions();
        options.setSocketFactory(PemSsl.trustOnly().getSocketFactory());
        options.setConnectionTimeout(1);
        IMqttMessageListener listener = (topic, message) -> { };
        return new MqttSubscriptionLifecycle(client, options, "terminal/+/transactions", 1, listener, 1);
    }

    @Test
    void startsEvenThoughTheBrokerIsUnreachable() throws MqttException {
        MqttSubscriptionLifecycle lifecycle = lifecycle();

        assertThatCode(lifecycle::start).doesNotThrowAnyException();
        assertThat(lifecycle.isRunning()).isTrue();

        lifecycle.destroy();
        assertThat(lifecycle.isRunning()).isFalse();
    }

    @Test
    void canBeStoppedAndStartedAgainBeforeItIsDestroyed() throws MqttException {
        MqttSubscriptionLifecycle lifecycle = lifecycle();

        lifecycle.start();
        lifecycle.stop();
        assertThat(lifecycle.isRunning()).isFalse();
        assertThatCode(lifecycle::start).doesNotThrowAnyException();
        assertThat(lifecycle.isRunning()).isTrue();
        lifecycle.stop();
        lifecycle.destroy();
    }

    @Test
    void startingTwiceAndStoppingTwiceIsHarmless() throws MqttException {
        MqttSubscriptionLifecycle lifecycle = lifecycle();

        assertThatCode(() -> {
            lifecycle.start();
            lifecycle.start();
            lifecycle.stop();
            lifecycle.stop();
            lifecycle.destroy();
        }).doesNotThrowAnyException();
    }
}
