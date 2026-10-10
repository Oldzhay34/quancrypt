package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.outbound.EventPublisher;
import com.quancrypt.core.port.outbound.PublishFailedException;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * EventPublisher contract shared by the recording fake and HttpEventPublisher: an empty batch is accepted without a
 * call, an accepting receiver accepts exactly the batch's ids, a receiver that cannot take the batch is a
 * PublishFailedException (D-154c, D-156).
 */
public abstract class EventPublisherContract {

    /** A publisher whose receiver accepts everything. */
    protected abstract EventPublisher accepting();

    /** A publisher whose receiver is down. */
    protected abstract EventPublisher failing();

    private static OutboxRecord event() {
        return new OutboxRecord(UUID.randomUUID(), EventType.SCAN_COMPLETED, 1, new ProjectKey("a".repeat(64)),
                Instant.parse("2026-10-09T10:00:00Z"), Map.of("finding_count", 1));
    }

    @Test
    void anEmptyBatchIsAcceptedAsNothing() {
        assertThat(accepting().publish(List.of())).isEmpty();
    }

    @Test
    void anAcceptingReceiverAcceptsTheBatchIds() {
        List<OutboxRecord> batch = List.of(event(), event());

        assertThat(accepting().publish(batch)).containsExactlyInAnyOrder(batch.get(0).id(), batch.get(1).id());
    }

    @Test
    void aReceiverThatIsDownIsAPublishFailure() {
        assertThatThrownBy(() -> failing().publish(List.of(event()))).isInstanceOf(PublishFailedException.class);
    }
}
