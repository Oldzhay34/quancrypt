package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.exception.IllegalStateTransitionException;
import com.quancrypt.core.domain.model.PlanItemState;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.PlanItemStates;
import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PlanItemStateTest {

    private static final Set<String> ALLOWED = Set.of(
            "DISCOVERED>PLANNED", "PLANNED>APPROVED", "APPROVED>APPLIED", "APPLIED>VERIFIED", "APPLIED>ROLLED_BACK", "ROLLED_BACK>PLANNED");

    static Stream<Arguments> everyPair() {
        return Stream.of(PlanItemStateCode.values()).flatMap(from -> Stream.of(PlanItemStateCode.values())
                .map(to -> Arguments.of(from, to, ALLOWED.contains(from + ">" + to))));
    }

    @ParameterizedTest(name = "{0} -> {1} allowed={2}")
    @MethodSource("everyPair")
    void everyOfThe36PairsIsAllowedOrForbiddenExactlyAsCryptoDomainSays(PlanItemStateCode from, PlanItemStateCode to, boolean allowed) {
        PlanItemState state = PlanItemStates.of(from);
        assertThat(state.canTransitionTo(to)).isEqualTo(allowed);
        if (allowed) {
            assertThat(state.transitionTo(to).code()).isEqualTo(to);
        } else {
            assertThatThrownBy(() -> state.transitionTo(to))
                    .isInstanceOf(IllegalStateTransitionException.class)
                    .hasMessageContaining(from + " -> " + to);
        }
    }

    @Test
    void sixStateClassesExistOneForEachCode() {
        for (PlanItemStateCode code : PlanItemStateCode.values()) {
            assertThat(PlanItemStates.of(code).code()).isEqualTo(code);
        }
        assertThat(PlanItemStates.of(PlanItemStateCode.VERIFIED).allowedTargets()).isEmpty();
    }

    @Test
    void anIllegalTransitionExceptionKnowsBothStates() {
        IllegalStateTransitionException e = new IllegalStateTransitionException(PlanItemStateCode.DISCOVERED, PlanItemStateCode.VERIFIED);
        assertThat(e.from()).isEqualTo(PlanItemStateCode.DISCOVERED);
        assertThat(e.to()).isEqualTo(PlanItemStateCode.VERIFIED);
    }
}
