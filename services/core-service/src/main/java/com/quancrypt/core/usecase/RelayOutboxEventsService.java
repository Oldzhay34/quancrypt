package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsUseCase;
import com.quancrypt.core.port.inbound.view.RelayResult;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.EventPublisher;
import com.quancrypt.core.port.outbound.IdempotencyStore;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.OutboxRelayRepository;
import com.quancrypt.core.port.outbound.PublishFailedException;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Sends unsent outbox events on (at least once) and purges idempotency records older than 24 hours (D-136, D-139e). */
public final class RelayOutboxEventsService implements RelayOutboxEventsUseCase {

    static final int MAX_BATCH = 200;
    static final Duration IDEMPOTENCY_RETENTION = Duration.ofHours(24);

    private final TransactionRunner tx;
    private final OutboxRelayRepository relay;
    private final EventPublisher publisher;
    private final IdempotencyStore idempotencyStore;
    private final AuditRecorder audit;
    private final Clock clock;

    public RelayOutboxEventsService(
            TransactionRunner tx, OutboxRelayRepository relay, EventPublisher publisher, IdempotencyStore idempotencyStore,
            AuditRecorder audit, Clock clock) {
        this.tx = tx;
        this.relay = relay;
        this.publisher = publisher;
        this.idempotencyStore = idempotencyStore;
        this.audit = audit;
        this.clock = clock;
    }

    @Override
    public RelayResult execute(RelayOutboxEventsCommand input) {
        if (input.batchSize() < 1 || input.batchSize() > MAX_BATCH) {
            throw Fail.validation("batchSize must be 1.." + MAX_BATCH);
        }
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            List<OutboxRecord> pending = relay.lockPending(input.batchSize());
            boolean[] failed = {false};
            Set<UUID> accepted = send(pending, failed);
            Instant now = clock.now();
            if (!accepted.isEmpty()) {
                relay.markPublished(accepted, now);
            }
            idempotencyStore.deleteOlderThan(now.minus(IDEMPOTENCY_RETENTION));
            if (!accepted.isEmpty()) {
                audit.record(AuditAction.OUTBOX_EVENTS_RELAYED, Optional.empty(), Optional.empty(), CallerKind.INTERNAL);
            }
            return new RelayResult(accepted.size(), relay.countPending(), failed[0]);
        });
    }

    /** A receiver that fails leaves the rows unsent; only ids of the batch count as accepted. */
    private Set<UUID> send(List<OutboxRecord> pending, boolean[] failed) {
        if (pending.isEmpty()) {
            return Set.of();
        }
        try {
            Set<UUID> sent = pending.stream().map(OutboxRecord::id).collect(Collectors.toSet());
            return publisher.publish(pending).stream().filter(sent::contains).collect(Collectors.toSet());
        } catch (PublishFailedException e) {
            failed[0] = true;
            return Set.of();
        }
    }
}
