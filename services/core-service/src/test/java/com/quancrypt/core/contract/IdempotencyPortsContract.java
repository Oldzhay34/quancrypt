package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.port.outbound.IdempotencyStore.Begin;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** IdempotencyStore (D-144). */
public abstract class IdempotencyPortsContract extends PortContract {

    private static final String DIGEST = "a".repeat(64);
    private static final String OTHER_DIGEST = "b".repeat(64);

    @Test
    void firstBeginIsFreshThenReplayOrConflict() {
        UUID resource = ids.next();

        assertThat(ports.idempotency().begin("key-1", AuditAction.SCAN_STARTED, DIGEST, at(1))).isInstanceOf(Begin.Fresh.class);
        ports.idempotency().complete("key-1", AuditAction.SCAN_STARTED, 201, Optional.of(resource));

        Begin replay = ports.idempotency().begin("key-1", AuditAction.SCAN_STARTED, DIGEST, at(2));
        assertThat(replay).isInstanceOf(Begin.Replay.class);
        Begin.Replay r = (Begin.Replay) replay;
        assertThat(r.record().statusCode()).isEqualTo(201);
        assertThat(r.record().resourceId()).contains(resource);
        assertThat(r.record().createdAt()).isEqualTo(at(1));
        assertThat(ports.idempotency().begin("key-1", AuditAction.SCAN_STARTED, OTHER_DIGEST, at(3))).isInstanceOf(Begin.Conflict.class);
        assertThat(ports.idempotency().begin("key-1", AuditAction.PLAN_CREATED, OTHER_DIGEST, at(3))).isInstanceOf(Begin.Fresh.class);
    }

    @Test
    void recordsOlderThanTheCutoffAreDeleted() {
        ports.idempotency().begin("old", AuditAction.SCAN_STARTED, DIGEST, at(1));
        ports.idempotency().begin("new", AuditAction.SCAN_STARTED, DIGEST, at(10));

        assertThat(ports.idempotency().deleteOlderThan(at(5))).isEqualTo(1);
        assertThat(ports.idempotency().begin("old", AuditAction.SCAN_STARTED, OTHER_DIGEST, at(11))).isInstanceOf(Begin.Fresh.class);
        assertThat(ports.idempotency().begin("new", AuditAction.SCAN_STARTED, OTHER_DIGEST, at(11))).isInstanceOf(Begin.Conflict.class);
    }
}
