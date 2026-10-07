package com.quancrypt.qbank.payment.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.qbank.payment.infrastructure.time.SystemClock;
import com.quancrypt.qbank.payment.infrastructure.time.UuidIdGenerator;
import com.quancrypt.qbank.payment.port.outbound.Clock;
import com.quancrypt.qbank.payment.port.outbound.IdGenerator;
import com.quancrypt.qbank.payment.support.Fakes.FixedClock;
import com.quancrypt.qbank.payment.support.Fakes.SequentialIdGenerator;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** Contract of Clock: every implementation must pass (Liskov substitution). */
abstract class ClockContractTest {

    abstract Clock create();

    @Test
    void neverReturnsNullAndNeverGoesBackwards() {
        Clock clock = create();

        Instant first = clock.now();
        Instant second = clock.now();

        assertThat(first).isNotNull();
        assertThat(second).isAfterOrEqualTo(first);
    }
}

class FixedClockContractTest extends ClockContractTest {

    @Override
    Clock create() {
        return new FixedClock(Instant.parse("2026-10-07T10:00:00Z"));
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

/** Contract of IdGenerator: every implementation must pass (Liskov substitution). */
abstract class IdGeneratorContractTest {

    abstract IdGenerator create();

    @Test
    void everyIdIsNewAndNeverNull() {
        IdGenerator generator = create();

        UUID first = generator.newId();
        UUID second = generator.newId();

        assertThat(first).isNotNull();
        assertThat(second).isNotNull().isNotEqualTo(first);
    }
}

class SequentialIdGeneratorContractTest extends IdGeneratorContractTest {

    @Override
    IdGenerator create() {
        return new SequentialIdGenerator();
    }
}

class UuidIdGeneratorContractTest extends IdGeneratorContractTest {

    @Override
    IdGenerator create() {
        return new UuidIdGenerator();
    }

    @Test
    void generatesRandomVersionFourUuids() {
        assertThat(create().newId().version()).isEqualTo(4);
    }
}
