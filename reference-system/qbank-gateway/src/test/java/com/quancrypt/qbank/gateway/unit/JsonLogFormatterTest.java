package com.quancrypt.qbank.gateway.unit;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.LoggingEvent;
import com.quancrypt.qbank.gateway.infrastructure.observability.JsonLogFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class JsonLogFormatterTest {

    private final JsonLogFormatter formatter =
            new JsonLogFormatter(new MockEnvironment().withProperty("spring.application.name", "svc"));
    private final Logger logger = new LoggerContext().getLogger("test");
    private final JsonMapper mapper = JsonMapper.builder().build();

    private LoggingEvent event(String message, Throwable throwable, Map<String, String> mdc) {
        LoggingEvent event = new LoggingEvent(Logger.class.getName(), logger, Level.INFO, message, throwable, null);
        event.setMDCPropertyMap(mdc);
        return event;
    }

    private static List<String> fieldNames(JsonNode node) {
        List<String> names = new ArrayList<>();
        node.propertyNames().forEach(names::add);
        return names;
    }

    @Test
    void emitsExactlyTheFiveRequiredFieldsInOrder() throws Exception {
        String line = formatter.format(event("hello", null, Map.of("traceId", "abc-123")));

        assertThat(line).endsWith("\n");
        JsonNode json = mapper.readTree(line);
        assertThat(fieldNames(json)).containsExactly("timestamp", "level", "service", "traceId", "message");
        assertThat(json.get("level").asString()).isEqualTo("INFO");
        assertThat(json.get("service").asString()).isEqualTo("svc");
        assertThat(json.get("traceId").asString()).isEqualTo("abc-123");
        assertThat(json.get("message").asString()).isEqualTo("hello");
        assertThat(json.get("timestamp").asString()).matches("\\d{4}-\\d{2}-\\d{2}T.*Z");
    }

    @Test
    void traceIdIsNullOutsideARequest() throws Exception {
        JsonNode json = mapper.readTree(formatter.format(event("no request", null, Map.of())));

        assertThat(json.get("traceId").isNull()).isTrue();
    }

    @Test
    void escapesQuotesBackslashesAndControlCharactersSoTheLineStaysOneJsonObject() throws Exception {
        String nasty = "a\"b\\c\nd\re\tf\u0001g h";

        String line = formatter.format(event(nasty, null, Map.of()));

        assertThat(line.trim().split("\n")).hasSize(1);
        assertThat(mapper.readTree(line).get("message").asString()).isEqualTo(nasty);
    }

    @Test
    void anExceptionContributesOnlyItsClassName() throws Exception {
        IllegalStateException exception = new IllegalStateException("secret-value-from-exception");

        JsonNode json = mapper.readTree(formatter.format(event("failed", exception, Map.of())));

        assertThat(json.get("message").asString())
                .contains("failed")
                .contains("java.lang.IllegalStateException")
                .doesNotContain("secret-value-from-exception");
    }
}
