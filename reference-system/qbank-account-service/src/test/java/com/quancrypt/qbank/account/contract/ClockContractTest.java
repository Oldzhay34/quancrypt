package com.quancrypt.qbank.account.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.account.infrastructure.time.SystemClock;
import com.quancrypt.qbank.account.port.outbound.Clock;
import com.quancrypt.qbank.account.support.FixedClock;
import com.quancrypt.qbank.account.support.TestData;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/** Every Clock implementation must pass these tests (Liskov substitution). */
abstract class ClockContractTest {

    abstract Clock create();

    @Test
    void neverReturnsNull() {
        assertThat(create().now()).isNotNull();
    }

    @Test
    void timeNeverGoesBackwards() {
        Clock clock = create();

        Instant first = clock.now();
        Instant second = clock.now();

        assertThat(second).isAfterOrEqualTo(first);
    }
}

class FixedClockContractTest extends ClockContractTest {

    @Override
    Clock create() {
        return new FixedClock(TestData.NOW);
    }
}

class SystemClockContractTest extends ClockContractTest {

    @Override
    Clock create() {
        return new SystemClock();
    }

    @Test
    void isCloseToTheSystemTime() {
        assertThat(create().now()).isBetween(Instant.now().minusSeconds(5), Instant.now().plusSeconds(5));
    }
}
