package com.quancrypt.core.infrastructure.outbox;

import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.port.outbound.EventPublisher;
import com.quancrypt.core.port.outbound.PublishFailedException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Sends a batch of event envelopes to the data platform's ingest-api (INGEST_API_URL) as one JSON array. A 2xx answer
 * accepts the whole batch; any other answer, a timeout, an I/O error or an open circuit is a PublishFailedException and
 * the events stay pending (D-156). The ingest-api contract is fixed in P6.1.
 */
public final class HttpEventPublisher implements EventPublisher {

    private final HttpClient client;
    private final Optional<URI> ingestUrl;
    private final Duration requestTimeout;
    private final CircuitBreaker circuitBreaker;
    private final OutboxJson json;

    public HttpEventPublisher(HttpClient client, Optional<URI> ingestUrl, Duration requestTimeout, CircuitBreaker circuitBreaker,
                              OutboxJson json) {
        this.client = client;
        this.ingestUrl = ingestUrl;
        this.requestTimeout = requestTimeout;
        this.circuitBreaker = circuitBreaker;
        this.json = json;
    }

    /**
     * Parses INGEST_API_URL: empty means not configured; otherwise only an absolute http or https URL with a host and
     * without user info is accepted. The error never repeats the value, which could carry credentials.
     */
    public static Optional<URI> ingestUrl(String raw) {
        if (raw == null || raw.isBlank()) {
            return Optional.empty();
        }
        URI uri;
        try {
            uri = new URI(raw.strip());
        } catch (URISyntaxException e) {
            throw new IllegalStateException("INGEST_API_URL is not a valid URL");
        }
        boolean httpScheme = "http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme());
        if (!httpScheme || uri.getHost() == null || uri.getRawUserInfo() != null) {
            throw new IllegalStateException("INGEST_API_URL must be an http or https URL with a host and without credentials");
        }
        return Optional.of(uri);
    }

    @Override
    public Set<UUID> publish(List<OutboxRecord> batch) {
        if (batch.isEmpty()) {
            return Set.of();
        }
        URI url = ingestUrl.orElseThrow(() -> new PublishFailedException("INGEST_API_URL is not configured"));
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(requestTimeout)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json.envelopes(batch)))
                .build();
        try {
            circuitBreaker.executeRunnable(() -> send(request));
        } catch (CallNotPermittedException e) {
            throw new PublishFailedException("circuit breaker is open");
        }
        return batch.stream().map(OutboxRecord::id).collect(Collectors.toUnmodifiableSet());
    }

    private void send(HttpRequest request) {
        HttpResponse<Void> response;
        try {
            response = client.send(request, HttpResponse.BodyHandlers.discarding());
        } catch (IOException e) {
            throw new PublishFailedException("ingest-api is unreachable: " + e.getClass().getSimpleName());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new PublishFailedException("interrupted while sending events");
        }
        if (response.statusCode() / 100 != 2) {
            throw new PublishFailedException("ingest-api answered " + response.statusCode());
        }
    }
}
