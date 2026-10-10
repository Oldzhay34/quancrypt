package com.quancrypt.core.infrastructure.config;

import com.quancrypt.core.infrastructure.anonymization.HmacEventAnonymizer;
import com.quancrypt.core.infrastructure.anonymization.RedactionRules;
import com.quancrypt.core.infrastructure.anonymization.Redactor;
import com.quancrypt.core.infrastructure.outbox.HttpEventPublisher;
import com.quancrypt.core.infrastructure.outbox.OutboxJson;
import com.quancrypt.core.port.outbound.EventPublisher;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Composition root of the outbox side: anonymization, redaction, payload JSON and the HTTP publisher. */
@Configuration(proxyBeanMethods = false)
public class OutboxConfig {

    @Bean
    OutboxJson outboxJson() {
        return new OutboxJson();
    }

    @Bean
    Redactor redactor() {
        return new Redactor(RedactionRules.fromClasspath());
    }

    /** Implements both EventAnonymizer and ProjectKeyHasher; the salt stays in this one object. */
    @Bean
    HmacEventAnonymizer hmacEventAnonymizer(@Value("${quancrypt.anon-salt}") String salt, Redactor redactor) {
        return new HmacEventAnonymizer(salt, redactor);
    }

    @Bean
    EventPublisher eventPublisher(
            OutboxJson json,
            @Value("${quancrypt.outbox.ingest-url:}") String ingestUrl,
            @Value("${quancrypt.outbox.relay.enabled:false}") boolean relayEnabled,
            @Value("${quancrypt.outbox.connect-timeout:2s}") Duration connectTimeout,
            @Value("${quancrypt.outbox.request-timeout:5s}") Duration requestTimeout) {
        Optional<URI> url = HttpEventPublisher.ingestUrl(ingestUrl);
        if (relayEnabled && url.isEmpty()) {
            throw new IllegalStateException("OUTBOX_RELAY_ENABLED=true needs INGEST_API_URL");
        }
        HttpClient client = HttpClient.newBuilder().connectTimeout(connectTimeout).followRedirects(HttpClient.Redirect.NEVER).build();
        CircuitBreaker breaker = CircuitBreaker.of("ingest-api", CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build());
        return new HttpEventPublisher(client, url, requestTimeout, breaker, json);
    }
}
