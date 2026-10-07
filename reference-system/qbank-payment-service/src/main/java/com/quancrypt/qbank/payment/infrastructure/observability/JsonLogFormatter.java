package com.quancrypt.qbank.payment.infrastructure.observability;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.spi.IThrowableProxy;
import java.time.Instant;
import org.springframework.boot.logging.structured.StructuredLogFormatter;
import org.springframework.core.env.Environment;

/**
 * One JSON object per log line with exactly the fields timestamp, level, service, traceId and message. A logged
 * exception contributes only its class name, never its message or stack trace.
 */
public class JsonLogFormatter implements StructuredLogFormatter<ILoggingEvent> {

    private static final String TRACE_ID_KEY = "traceId";

    private final String service;

    public JsonLogFormatter(Environment environment) {
        this.service = environment.getProperty("spring.application.name", "qbank-payment-service");
    }

    @Override
    public String format(ILoggingEvent event) {
        String traceId = event.getMDCPropertyMap().get(TRACE_ID_KEY);
        StringBuilder json = new StringBuilder(256);
        json.append("{\"timestamp\":");
        appendString(json, Instant.ofEpochMilli(event.getTimeStamp()).toString());
        json.append(",\"level\":");
        appendString(json, event.getLevel().toString());
        json.append(",\"service\":");
        appendString(json, service);
        json.append(",\"traceId\":");
        if (traceId == null) {
            json.append("null");
        } else {
            appendString(json, traceId);
        }
        json.append(",\"message\":");
        appendString(json, message(event));
        return json.append("}\n").toString();
    }

    private static String message(ILoggingEvent event) {
        IThrowableProxy throwable = event.getThrowableProxy();
        if (throwable == null) {
            return event.getFormattedMessage();
        }
        return event.getFormattedMessage() + " [" + throwable.getClassName() + "]";
    }

    static void appendString(StringBuilder json, String value) {
        json.append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> json.append("\\\"");
                case '\\' -> json.append("\\\\");
                case '\n' -> json.append("\\n");
                case '\r' -> json.append("\\r");
                case '\t' -> json.append("\\t");
                default -> {
                    if (c < 0x20 || c == ' ' || c == ' ') {
                        json.append(String.format("\\u%04x", (int) c));
                    } else {
                        json.append(c);
                    }
                }
            }
        }
        json.append('"');
    }
}
