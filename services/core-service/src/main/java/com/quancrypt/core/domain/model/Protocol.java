package com.quancrypt.core.domain.model;

/** Link protocol; TLS is a separate flag. */
public enum Protocol {
    HTTP,
    GRPC,
    MQTT,
    AMQP,
    KAFKA,
    OTHER;
}
