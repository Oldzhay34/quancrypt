package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.outbound.OutboxRelayRepository;
import com.quancrypt.core.port.outbound.OutboxWriter;
import java.time.Instant;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;

/** The transactional outbox and the relay's view of it. */
public final class FakeOutbox implements OutboxWriter, OutboxRelayRepository {

    private final InMemoryDatabase db;

    public FakeOutbox(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public void append(OutboxRecord record) {
        db.outbox.add(record);
    }

    @Override
    public int deletePendingExceptRevocations(ProjectKey projectKey) {
        List<OutboxRecord> doomed = db.outbox.stream()
                .filter(r -> r.projectKey().equals(projectKey) && !db.published.contains(r.id()) && r.type() != EventType.CONSENT_REVOKED)
                .toList();
        db.outbox.removeAll(doomed);
        return doomed.size();
    }

    @Override
    public List<OutboxRecord> lockPending(int limit) {
        return db.outbox.stream().filter(r -> !db.published.contains(r.id()))
                .sorted(Comparator.comparing(OutboxRecord::occurredAt).thenComparing(OutboxRecord::id)).limit(limit).toList();
    }

    @Override
    public void markPublished(Collection<UUID> ids, Instant at) {
        db.published.addAll(ids);
    }

    @Override
    public long countPending() {
        return db.outbox.stream().filter(r -> !db.published.contains(r.id())).count();
    }
}
