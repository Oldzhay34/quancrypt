package com.quancrypt.core.api.scheduler;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.facade.OutboxRelayFacade;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsUseCase;
import com.quancrypt.core.port.inbound.view.RelayResult;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Unit test of the relay trigger (same package for its package-private probes). The relay trigger's exponential backoff (D-156): interval x 2^failures up to the maximum, reset after a success. */
class OutboxRelaySchedulerTest {

    /** A clock the test moves by hand. */
    private static final class MovableClock extends Clock {
        private Instant now = Instant.parse("2026-10-09T10:00:00Z");

        @Override
        public ZoneOffset getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return now;
        }

        void advance(Duration by) {
            now = now.plus(by);
        }
    }

    /** Answers scripted results and counts calls; an empty script means success. */
    private static final class ScriptedRelay implements RelayOutboxEventsUseCase {
        private final Deque<Object> script = new ArrayDeque<>();
        private final List<Integer> batchSizes = new ArrayList<>();

        @Override
        public RelayResult execute(RelayOutboxEventsCommand input) {
            batchSizes.add(input.batchSize());
            Object next = script.isEmpty() ? Boolean.FALSE : script.poll();
            if (next instanceof RuntimeException e) {
                throw e;
            }
            return new RelayResult(0, 0, (Boolean) next);
        }
    }

    private final MovableClock clock = new MovableClock();
    private final ScriptedRelay relay = new ScriptedRelay();
    private final OutboxRelayScheduler scheduler = new OutboxRelayScheduler(new OutboxRelayFacade(relay), 100,
            Duration.ofSeconds(5), Duration.ofMinutes(5), clock);

    @Test
    void backoffDoublesUpToTheMaximum() {
        assertThat(scheduler.backoff(1)).isEqualTo(Duration.ofSeconds(10));
        assertThat(scheduler.backoff(2)).isEqualTo(Duration.ofSeconds(20));
        assertThat(scheduler.backoff(5)).isEqualTo(Duration.ofSeconds(160));
        assertThat(scheduler.backoff(6)).isEqualTo(Duration.ofMinutes(5));
        assertThat(scheduler.backoff(40)).isEqualTo(Duration.ofMinutes(5));
    }

    @Test
    void failedRunsWaitAndASuccessResets() {
        relay.script.add(Boolean.TRUE);
        relay.script.add(new IllegalStateException("database down"));

        scheduler.tick();
        assertThat(scheduler.nextRunAt()).isEqualTo(clock.instant().plusSeconds(10));
        clock.advance(Duration.ofSeconds(5));
        scheduler.tick();
        assertThat(relay.batchSizes).hasSize(1);

        clock.advance(Duration.ofSeconds(5));
        scheduler.tick();
        assertThat(relay.batchSizes).hasSize(2);
        assertThat(scheduler.nextRunAt()).isEqualTo(clock.instant().plusSeconds(20));

        clock.advance(Duration.ofSeconds(20));
        scheduler.tick();
        assertThat(relay.batchSizes).containsExactly(100, 100, 100);
        assertThat(scheduler.nextRunAt()).isEqualTo(Instant.MIN);
    }
}
