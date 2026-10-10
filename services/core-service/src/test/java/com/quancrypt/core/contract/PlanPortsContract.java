package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.PlanAlreadyExistsException;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.PlanItemTransition;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.RiskClass;
import com.quancrypt.core.domain.model.RiskFactor;
import com.quancrypt.core.domain.model.RiskScore;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.policy.RiskClassPolicy;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** PlanReader, PlanWriter and RiskThresholdReader. */
public abstract class PlanPortsContract extends PortContract {

    private record Fixture(Tree tree, Plan plan, PlanItem high, PlanItem low) {
    }

    private PlanItem planned(Plan plan, Finding finding, double score, List<RiskFactor> factors) {
        return PlanItem.discovered(ids.next(), plan.id(), finding.id(), StrategyCode.HYBRID_TLS_KEX, Effort.M, RiskScore.of(score), factors)
                .transitionTo(PlanItemStateCode.PLANNED);
    }

    private PlanItemTransition firstTransition(PlanItem item) {
        return new PlanItemTransition(ids.next(), item.id(), PlanItemStateCode.DISCOVERED, PlanItemStateCode.PLANNED, at(5), CallerKind.UI);
    }

    private Fixture plannedFixture() {
        Tree tree = tree();
        Finding a = finding(tree.file().id(), "Tls#a", Priority.P1, 10);
        Finding b = finding(tree.file().id(), "Tls#b", Priority.P1, 20);
        ports.findingWriter().insertIgnoringDuplicates(List.of(a, b));
        Plan plan = new Plan(ids.next(), tree.scan().id(), at(4));
        ports.planWriter().insert(plan);
        PlanItem high = planned(plan, a, 0.9, List.of(
                new RiskFactor(1, "algorithm_weakness", new BigDecimal("0.400000")),
                new RiskFactor(2, "exposure", new BigDecimal("-0.125000"))));
        PlanItem low = planned(plan, b, 0.2, List.of());
        ports.planWriter().insertItems(List.of(high, low), List.of(firstTransition(high), firstTransition(low)));
        return new Fixture(tree, plan, high, low);
    }

    @Test
    void planAndItemsRoundTrip() {
        Fixture f = plannedFixture();

        assertThat(ports.planReader().byScan(f.tree().scan().id())).contains(f.plan());
        assertThat(ports.planReader().allItems(f.plan().id())).containsExactlyInAnyOrder(f.high(), f.low());
        assertThat(ports.planReader().item(f.high().id())).contains(f.high());
        assertThat(ports.planReader().projectIdOfItem(f.high().id())).contains(f.tree().project().id());
        assertThat(ports.planReader().items(f.plan().id(), Optional.empty(), 0, 1).total()).isEqualTo(2);
        assertThat(ports.planReader().items(f.plan().id(), Optional.of(PlanItemStateCode.APPROVED), 0, 10).items()).isEmpty();
    }

    @Test
    void secondPlanForTheSameScanIsRejected() {
        Fixture f = plannedFixture();

        assertThatThrownBy(() -> ports.planWriter().insert(new Plan(ids.next(), f.tree().scan().id(), at(6))))
                .isInstanceOf(PlanAlreadyExistsException.class);
    }

    @Test
    void updateNeedsTheStoredVersion() {
        Fixture f = plannedFixture();
        PlanItem approved = f.high().transitionTo(PlanItemStateCode.APPROVED);
        PlanItemTransition transition = new PlanItemTransition(ids.next(), f.high().id(), PlanItemStateCode.PLANNED,
                PlanItemStateCode.APPROVED, at(7), CallerKind.UI);

        ports.planWriter().update(approved, f.high().version(), transition);

        assertThat(ports.planReader().item(f.high().id())).contains(approved);
        assertThat(ports.planReader().items(f.plan().id(), Optional.of(PlanItemStateCode.APPROVED), 0, 10).items()).containsExactly(approved);
        PlanItemTransition again = new PlanItemTransition(ids.next(), f.high().id(), PlanItemStateCode.PLANNED,
                PlanItemStateCode.APPROVED, at(8), CallerKind.UI);
        assertThatThrownBy(() -> ports.planWriter().update(approved, f.high().version(), again))
                .isInstanceOf(ConcurrentModificationException.class);
    }

    @Test
    void riskThresholdsMatchTheLookup() {
        RiskClassPolicy policy = ports.riskThresholds().policy();

        assertThat(policy.classify(RiskScore.of(0.80))).isEqualTo(RiskClass.CRITICAL);
        assertThat(policy.classify(RiskScore.of(0.7999))).isEqualTo(RiskClass.HIGH);
        assertThat(policy.classify(RiskScore.of(0.60))).isEqualTo(RiskClass.HIGH);
        assertThat(policy.classify(RiskScore.of(0.35))).isEqualTo(RiskClass.MEDIUM);
        assertThat(policy.classify(RiskScore.of(0.3499))).isEqualTo(RiskClass.LOW);
        assertThat(policy.classify(RiskScore.of(0))).isEqualTo(RiskClass.LOW);
    }
}
