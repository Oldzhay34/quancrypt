package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.EventPublisherContract;
import com.quancrypt.core.infrastructure.outbox.HttpEventPublisher;
import com.quancrypt.core.infrastructure.outbox.OutboxJson;
import com.quancrypt.core.integration.support.IngestApiStub;
import com.quancrypt.core.port.outbound.EventPublisher;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;

/** HttpEventPublisher against a loopback ingest-api stub, under the EventPublisher contract. */
class HttpEventPublisherContractTest extends EventPublisherContract {

    private final IngestApiStub stub = new IngestApiStub();

    @AfterEach
    void stop() {
        stub.close();
    }

    private EventPublisher publisher() {
        return new HttpEventPublisher(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build(), Optional.of(URI.create(stub.url())),
                Duration.ofSeconds(2), CircuitBreaker.ofDefaults("contract"), new OutboxJson());
    }

    @Override
    protected EventPublisher accepting() {
        stub.answer(202);
        return publisher();
    }

    @Override
    protected EventPublisher failing() {
        stub.answer(503);
        return publisher();
    }
}
