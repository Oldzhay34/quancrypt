package com.quancrypt.analyzer.domain.model;

/** Protocol of a topology edge; the same list as core-service's links (D-178e). */
public enum Protocol {
    HTTP, GRPC, MQTT, AMQP, KAFKA, OTHER
}
