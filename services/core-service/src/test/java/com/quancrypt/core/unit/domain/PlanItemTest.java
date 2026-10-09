package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.exception.IllegalStateTransitionException;
import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.RiskFactor;
import com.quancrypt.core.domain.model.RiskScore;
import com.quancrypt.core.domain.model.StrategyCode;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PlanItemTest {

    private PlanItem discovered() {
        return PlanItem.discovered(new UUID(0, 1), new UUID(0, 2), new UUID(0, 3), StrategyCode.HYBRID_TLS_KEX, Effort.M,
                RiskScore.of(0.5), List.of(new RiskFactor(1, "feature", new BigDecimal("0.1"))));
    }

    @Test
    void aNewItemIsDiscoveredWithVersionZero() {
        PlanItem item = discovered();
        assertThat(item.state().code()).isEqualTo(PlanItemStateCode.DISCOVERED);
        assertThat(item.version()).isZero();
    }

    @Test
    void everyTransitionBumpsTheVersionAndWalksTheHappyPath() {
        PlanItem item = discovered().transitionTo(PlanItemStateCode.PLANNED);
        assertThat(item.version()).isEqualTo(1);
        item = item.transitionTo(PlanItemStateCode.APPROVED).transitionTo(PlanItemStateCode.APPLIED).transitionTo(PlanItemStateCode.VERIFIED);
        assertThat(item.state().code()).isEqualTo(PlanItemStateCode.VERIFIED);
        assertThat(item.version()).isEqualTo(4);
    }

    @Test
    void aRolledBackItemCanBePlannedAgain() {
        PlanItem item = discovered().transitionTo(PlanItemStateCode.PLANNED).transitionTo(PlanItemStateCode.APPROVED)
                .transitionTo(PlanItemStateCode.APPLIED).transitionTo(PlanItemStateCode.ROLLED_BACK).transitionTo(PlanItemStateCode.PLANNED);
        assertThat(item.state().code()).isEqualTo(PlanItemStateCode.PLANNED);
    }

    @Test
    void anIllegalTransitionLeavesTheItemUntouched() {
        PlanItem item = discovered();
        assertThatThrownBy(() -> item.transitionTo(PlanItemStateCode.APPLIED)).isInstanceOf(IllegalStateTransitionException.class);
        assertThat(item.state().code()).isEqualTo(PlanItemStateCode.DISCOVERED);
        assertThat(item.version()).isZero();
    }
}
