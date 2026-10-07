package com.quancrypt.qbank.payment.infrastructure.config;

import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.IMqttMessageListener;
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.SmartLifecycle;

/**
 * Keeps one MQTT subscription alive for the life of the service (D-98). The service starts even when the broker is
 * unreachable: the first connection is retried at a fixed interval (Paho's automatic reconnect only works after a
 * first successful connection) and every established connection subscribes again.
 *
 * <p>The lifecycle can be stopped and started again (Spring pauses and resumes cached test contexts, and a
 * context may be stopped and restarted): {@link #stop()} only disconnects, the client is closed in {@link #destroy()}.
 */
final class MqttSubscriptionLifecycle implements SmartLifecycle, DisposableBean {

    private static final Logger LOG = LoggerFactory.getLogger(MqttSubscriptionLifecycle.class);
    private static final int DISCONNECT_TIMEOUT_MS = 3000;

    private final MqttClient client;
    private final MqttConnectOptions options;
    private final String topicFilter;
    private final int qos;
    private final IMqttMessageListener listener;
    private final long retrySeconds;
    private volatile ScheduledExecutorService scheduler;
    private volatile boolean running;

    MqttSubscriptionLifecycle(
            MqttClient client,
            MqttConnectOptions options,
            String topicFilter,
            int qos,
            IMqttMessageListener listener,
            long retrySeconds) {
        this.client = client;
        this.options = options;
        this.topicFilter = topicFilter;
        this.qos = qos;
        this.listener = listener;
        this.retrySeconds = retrySeconds;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        client.setCallback(new MqttCallbackExtended() {
            @Override
            public void connectComplete(boolean reconnect, String serverUri) {
                LOG.info("mqtt connected reconnect={}", reconnect);
                // Subscribing from inside a callback would block the callback thread; hand it to the scheduler.
                submit(MqttSubscriptionLifecycle.this::subscribe);
            }

            @Override
            public void connectionLost(Throwable cause) {
                LOG.warn("mqtt connection lost; automatic reconnect is on");
            }

            @Override
            public void messageArrived(String topic, MqttMessage message) throws Exception {
                // the listener swallows its own failures; an exception here would drop the connection
                listener.messageArrived(topic, message);
            }

            @Override
            public void deliveryComplete(IMqttDeliveryToken token) {
                // the service only subscribes, it never publishes
            }
        });
        scheduler = Executors.newSingleThreadScheduledExecutor(task -> {
            Thread thread = new Thread(task, "mqtt-subscription");
            thread.setDaemon(true);
            return thread;
        });
        submit(this::connect);
    }

    @Override
    public synchronized void stop() {
        running = false;
        ScheduledExecutorService current = scheduler;
        if (current != null) {
            current.shutdownNow();
        }
        try {
            if (client.isConnected()) {
                client.disconnect(DISCONNECT_TIMEOUT_MS);
            }
        } catch (MqttException e) {
            LOG.warn("mqtt disconnect failed reason={}", e.getReasonCode());
        }
    }

    @Override
    public void destroy() {
        stop();
        try {
            client.close();
        } catch (MqttException e) {
            LOG.warn("mqtt close failed reason={}", e.getReasonCode());
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    private void connect() {
        if (!running) {
            return;
        }
        try {
            client.connect(options);
        } catch (MqttException e) {
            LOG.warn("mqtt connect failed reason={}; retrying in {} s", e.getReasonCode(), retrySeconds);
            retryLater(this::connect);
        }
    }

    private void subscribe() {
        if (!running) {
            return;
        }
        try {
            client.subscribe(topicFilter, qos);
            LOG.info("mqtt subscribed qos={}", qos);
        } catch (MqttException e) {
            LOG.warn("mqtt subscribe failed reason={}; retrying in {} s", e.getReasonCode(), retrySeconds);
            retryLater(this::subscribe);
        }
    }

    private void submit(Runnable task) {
        ScheduledExecutorService current = scheduler;
        if (running && current != null && !current.isShutdown()) {
            try {
                current.execute(task);
            } catch (RejectedExecutionException e) {
                LOG.debug("mqtt task dropped because the lifecycle was stopped");
            }
        }
    }

    private void retryLater(Runnable task) {
        ScheduledExecutorService current = scheduler;
        if (running && current != null && !current.isShutdown()) {
            try {
                current.schedule(task, retrySeconds, TimeUnit.SECONDS);
            } catch (RejectedExecutionException e) {
                LOG.debug("mqtt retry dropped because the lifecycle was stopped");
            }
        }
    }
}
