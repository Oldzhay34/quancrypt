package com.quancrypt.analyzer.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.LoggingEvent;
import com.quancrypt.analyzer.infrastructure.observability.JsonLogFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** One JSON object per line, exactly five fields, and no secret in the message (guardrails-security section 5). */
class JsonLogFormatterTest {

    private static final JsonMapper JSON = JsonMapper.builder().build();
    private final JsonLogFormatter formatter = new JsonLogFormatter(new MockEnvironment().withProperty("spring.application.name", "analyzer-service"));
    private final LoggerContext context = new LoggerContext();

    private LoggingEvent event(String message, Throwable error, Object... arguments) {
        LoggingEvent event = new LoggingEvent("test", context.getLogger("t"), Level.INFO, message, error, arguments);
        event.setMDCPropertyMap(Map.of("traceId", "trace-1"));
        return event;
    }

    @Test
    void aLineHasExactlyTheFiveFields() {
        String line = formatter.format(event("request completed method={} status={}", null, "GET", 200));

        JsonNode json = JSON.readTree(line);
        List<String> names = new ArrayList<>();
        json.propertyNames().forEach(names::add);
        assertThat(names).containsExactly("timestamp", "level", "service", "traceId", "message");
        assertThat(json.get("service").asString()).isEqualTo("analyzer-service");
        assertThat(json.get("traceId").asString()).isEqualTo("trace-1");
        assertThat(json.get("message").asString()).isEqualTo("request completed method=GET status=200");
        assertThat(line).endsWith("\n").hasLineCount(1);
    }

    @Test
    void aSecretInTheMessageIsMaskedAndAnExceptionShowsOnlyItsClass() {
        String line = formatter.format(event("failed with password=hunter2hunter2 for {}", new IllegalStateException("secret detail"), "x"));

        assertThat(line).doesNotContain("hunter2hunter2").doesNotContain("secret detail");
        assertThat(JSON.readTree(line).get("message").asString()).contains("[REDACTED:").contains("[java.lang.IllegalStateException]");
    }

    @Test
    void aMessageWithoutATraceIdWritesNull() {
        LoggingEvent plain = new LoggingEvent("test", context.getLogger("t"), Level.WARN, "hello", null, new Object[0]);
        plain.setMDCPropertyMap(Map.of());

        JsonNode json = JSON.readTree(formatter.format(plain));
        assertThat(json.get("traceId").isNull()).isTrue();
        assertThat(json.get("level").asString()).isEqualTo("WARN");
    }

    @Test
    void controlCharactersAndLineBreaksAreEscapedSoOneEventIsOneLine() {
        String line = formatter.format(event("a\nb\tc d", null));

        assertThat(line).hasLineCount(1);
        assertThat(JSON.readTree(line).get("message").asString()).isEqualTo("a\nb\tc d");
    }
}
