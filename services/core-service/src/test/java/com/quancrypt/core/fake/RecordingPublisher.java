package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.port.outbound.EventPublisher;
import com.quancrypt.core.port.outbound.PublishFailedException;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Accepts or refuses events as the test says and remembers what it was given. */
public final class RecordingPublisher implements EventPublisher {

    private final List<OutboxRecord> seen = new ArrayList<>();
    private boolean acceptAll = true;
    private boolean failing;
    private boolean answerWithForeignId;

    public void acceptAll(boolean value) {
        this.acceptAll = value;
    }

    public void answerWithForeignId(boolean value) {
        this.answerWithForeignId = value;
    }

    public void failing(boolean value) {
        this.failing = value;
    }

    @Override
    public Set<UUID> publish(List<OutboxRecord> batch) {
        if (failing) {
            throw new PublishFailedException("receiver is down");
        }
        seen.addAll(batch);
        if (answerWithForeignId) {
            return Set.of(new UUID(8, 8));
        }
        return acceptAll ? batch.stream().map(OutboxRecord::id).collect(Collectors.toSet()) : Set.of();
    }

    public List<OutboxRecord> seen() {
        return List.copyOf(seen);
    }
}
