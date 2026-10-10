package com.quancrypt.core.api.scheduler;

import com.quancrypt.core.facade.OutboxRelayFacade;
import com.quancrypt.core.facade.dto.RelayOutcome;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * Scheduled driving adapter of the outbox relay (D-155, D-156). It ticks every interval; after a failed delivery it
 * waits interval x 2^failures (at most maxBackoff) before the next run and returns to the interval after a success.
 * Events never fail permanently: they stay pending until delivered. Only counts are logged, never event contents.
 */
public final class OutboxRelayScheduler {

    private static final Logger LOG = LoggerFactory.getLogger(OutboxRelayScheduler.class);

    private final OutboxRelayFacade relay;
    private final int batchSize;
    private final Duration interval;
    private final Duration maxBackoff;
    private final Clock clock;
    private int consecutiveFailures;
    private Instant nextRunAt = Instant.MIN;

    public OutboxRelayScheduler(OutboxRelayFacade relay, int batchSize, Duration interval, Duration maxBackoff, Clock clock) {
        if (interval.isNegative() || interval.isZero() || maxBackoff.compareTo(interval) < 0) {
            throw new IllegalArgumentException("relay interval must be positive and not longer than the maximum backoff");
        }
        this.relay = relay;
        this.batchSize = batchSize;
        this.interval = interval;
        this.maxBackoff = maxBackoff;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${quancrypt.outbox.relay.interval:5s}")
    public void tick() {
        Instant now = clock.instant();
        if (now.isBefore(nextRunAt)) {
            return;
        }
        boolean failed;
        try {
            RelayOutcome outcome = relay.relay(batchSize);
            failed = outcome.publishFailed();
            if (outcome.relayedCount() > 0) {
                LOG.info("outbox relay sent {} events, {} pending", outcome.relayedCount(), outcome.remainingCount());
            }
        } catch (RuntimeException e) {
            LOG.warn("outbox relay run failed: {}", e.getClass().getSimpleName());
            failed = true;
        }
        if (failed) {
            consecutiveFailures++;
            Duration wait = backoff(consecutiveFailures);
            nextRunAt = now.plus(wait);
            LOG.warn("outbox delivery failed {} times in a row, next attempt in {} s", consecutiveFailures, wait.toSeconds());
        } else {
            consecutiveFailures = 0;
            nextRunAt = Instant.MIN;
        }
    }

    /** interval x 2^failures, capped at maxBackoff. */
    Duration backoff(int failures) {
        Duration wait = interval;
        for (int i = 0; i < failures && wait.compareTo(maxBackoff) < 0; i++) {
            wait = wait.multipliedBy(2);
        }
        return wait.compareTo(maxBackoff) > 0 ? maxBackoff : wait;
    }

    Instant nextRunAt() {
        return nextRunAt;
    }
}
