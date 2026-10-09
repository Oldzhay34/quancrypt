package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/** One scan of a project; at most one scan per project runs at a time. */
public record Scan(
        UUID id,
        UUID projectId,
        Optional<Integer> runtimeProfileSequenceNo,
        ScanStatus status,
        Instant startedAt,
        Optional<Instant> completedAt) {

    public Scan {
        if ((status == ScanStatus.RUNNING) != completedAt.isEmpty()) {
            throw new IllegalArgumentException("a scan is completed exactly when it is not running");
        }
    }

    public static Scan start(UUID id, UUID projectId, Optional<Integer> profileSequenceNo, Instant at) {
        return new Scan(id, projectId, profileSequenceNo, ScanStatus.RUNNING, at, Optional.empty());
    }

    public boolean isRunning() {
        return status == ScanStatus.RUNNING;
    }

    public Scan finish(ScanStatus outcome, Instant at) {
        if (!isRunning() || outcome == ScanStatus.RUNNING) {
            throw new IllegalStateException("only a running scan can finish with COMPLETED or FAILED");
        }
        return new Scan(id, projectId, runtimeProfileSequenceNo, outcome, startedAt, Optional.of(at));
    }
}
