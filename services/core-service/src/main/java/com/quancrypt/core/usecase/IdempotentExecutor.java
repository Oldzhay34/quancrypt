package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.IdempotencyRecord;
import com.quancrypt.core.port.inbound.Idempotency;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IdempotencyStore;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;
import java.util.function.Supplier;

/** Runs a command at most once per Idempotency-Key and replays the result for a retry (D-144). */
public final class IdempotentExecutor {

    /** A command's result with what the idempotency record keeps. */
    record Outcome<R>(R value, int statusCode, Optional<UUID> resourceId) {
    }

    private final IdempotencyStore store;
    private final Clock clock;

    public IdempotentExecutor(IdempotencyStore store, Clock clock) {
        this.store = store;
        this.clock = clock;
    }

    <R> R execute(
            Optional<Idempotency> idempotency,
            AuditAction operation,
            Function<IdempotencyRecord, R> replay,
            Supplier<Outcome<R>> work) {
        if (idempotency.isEmpty()) {
            return work.get().value();
        }
        Idempotency request = idempotency.get();
        if (request.key() == null || request.key().isBlank() || request.key().length() > 128) {
            throw Fail.validation("Idempotency-Key must be 1..128 characters");
        }
        return switch (store.begin(request.key(), operation, request.requestDigest(), clock.now())) {
            case IdempotencyStore.Begin.Fresh fresh -> {
                Outcome<R> outcome = work.get();
                store.complete(request.key(), operation, outcome.statusCode(), outcome.resourceId());
                yield outcome.value();
            }
            case IdempotencyStore.Begin.Replay replayed -> replay.apply(replayed.record());
            case IdempotencyStore.Begin.Conflict conflict ->
                throw Fail.problem(ProblemCode.IDEMPOTENCY_CONFLICT, "the Idempotency-Key was used with a different request");
        };
    }
}
