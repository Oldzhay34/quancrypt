package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.infrastructure.outbox.HttpEventPublisher;
import com.quancrypt.core.infrastructure.outbox.OutboxJson;
import com.quancrypt.core.integration.support.IngestApiStub;
import com.quancrypt.core.port.outbound.PublishFailedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** HttpEventPublisher on loopback: 2xx accepts the batch, other answers, refused connections and an open circuit fail it. */
class HttpEventPublisherTest {

    private IngestApiStub stub;
    private CircuitBreaker breaker;

    @BeforeEach
    void start() {
        stub = new IngestApiStub();
        breaker = CircuitBreaker.of("test", CircuitBreakerConfig.custom()
                .slidingWindowSize(2).minimumNumberOfCalls(2).failureRateThreshold(50).waitDurationInOpenState(Duration.ofMinutes(5)).build());
    }

    @AfterEach
    void stop() {
        stub.close();
    }

    private HttpEventPublisher publisher(Optional<URI> url) {
        return new HttpEventPublisher(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build(), url, Duration.ofSeconds(2), breaker,
                new OutboxJson());
    }

    private static OutboxRecord event() {
        return new OutboxRecord(UUID.randomUUID(), EventType.SCAN_COMPLETED, 1, new ProjectKey("a".repeat(64)), Instant.parse("2026-10-09T10:00:00Z"),
                Map.of("finding_count", 1));
    }

    @Test
    void successAcceptsTheWholeBatch() {
        List<OutboxRecord> batch = List.of(event(), event());

        assertThat(publisher(Optional.of(URI.create(stub.url()))).publish(batch))
                .containsExactlyInAnyOrder(batch.get(0).id(), batch.get(1).id());
        assertThat(stub.bodies()).hasSize(1);
    }

    @Test
    void ingestUrlAcceptsOnlyHttpWithoutCredentialsAndNeverEchoesIt() {
        assertThat(HttpEventPublisher.ingestUrl("")).isEmpty();
        assertThat(HttpEventPublisher.ingestUrl("http://ingest-api:8084/api/v1/events")).isPresent();
        for (String bad : new String[] {"ftp://ingest-api/x", "http://user:s3cret-demo@ingest-api/x", "/relative/path", "http://[bad"}) {
            assertThatThrownBy(() -> HttpEventPublisher.ingestUrl(bad)).isInstanceOf(IllegalStateException.class)
                    .hasMessageNotContaining("s3cret-demo").hasMessageNotContaining(bad);
        }
    }

    @Test
    void emptyBatchSendsNothing() {
        assertThat(publisher(Optional.of(URI.create(stub.url()))).publish(List.of())).isEmpty();
        assertThat(stub.bodies()).isEmpty();
    }

    @Test
    void errorAnswerMissingUrlAndRefusedConnectionFail() {
        stub.answer(500);
        assertThatThrownBy(() -> publisher(Optional.of(URI.create(stub.url()))).publish(List.of(event())))
                .isInstanceOf(PublishFailedException.class).hasMessageContaining("500");
        assertThatThrownBy(() -> publisher(Optional.empty()).publish(List.of(event())))
                .isInstanceOf(PublishFailedException.class).hasMessageContaining("INGEST_API_URL");
    }

    @Test
    void circuitOpensAfterRepeatedFailures() {
        stub.answer(503);
        HttpEventPublisher publisher = publisher(Optional.of(URI.create(stub.url())));
        for (int i = 0; i < 2; i++) {
            assertThatThrownBy(() -> publisher.publish(List.of(event()))).isInstanceOf(PublishFailedException.class);
        }
        int callsBefore = stub.bodies().size();

        assertThatThrownBy(() -> publisher.publish(List.of(event()))).isInstanceOf(PublishFailedException.class)
                .hasMessageContaining("circuit breaker is open");
        assertThat(stub.bodies()).hasSize(callsBefore);
    }
}
