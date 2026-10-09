package com.quancrypt.core.fake;

import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.PlanAlreadyExistsException;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.PlanItemTransition;
import com.quancrypt.core.domain.model.RiskClass;
import com.quancrypt.core.domain.policy.RiskClassPolicy;
import com.quancrypt.core.port.outbound.PlanReader;
import com.quancrypt.core.port.outbound.PlanWriter;
import com.quancrypt.core.port.outbound.RiskThresholdReader;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/** Plans and plan items with optimistic updates, plus the risk thresholds of the lookup table. */
public final class FakePlans implements PlanReader, PlanWriter, RiskThresholdReader {

    private final InMemoryDatabase db;

    public FakePlans(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<Plan> byScan(UUID scanId) {
        return db.plans.values().stream().filter(p -> p.scanId().equals(scanId)).findFirst();
    }

    @Override
    public PageResult<PlanItem> items(UUID planId, Optional<PlanItemStateCode> state, int page, int size) {
        List<PlanItem> matching = allItems(planId).stream().filter(i -> state.map(s -> s == i.state().code()).orElse(true)).toList();
        return FakePaging.slice(matching, page, size);
    }

    @Override
    public List<PlanItem> allItems(UUID planId) {
        return db.planItems.values().stream().filter(i -> i.planId().equals(planId)).toList();
    }

    @Override
    public Optional<PlanItem> item(UUID itemId) {
        return Optional.ofNullable(db.planItems.get(itemId));
    }

    @Override
    public Optional<UUID> projectIdOfItem(UUID itemId) {
        return item(itemId).map(i -> db.plans.get(i.planId()).scanId()).map(db::projectOf);
    }

    @Override
    public void insert(Plan plan) {
        if (byScan(plan.scanId()).isPresent()) {
            throw new PlanAlreadyExistsException();
        }
        db.plans.put(plan.id(), plan);
    }

    @Override
    public void insertItems(List<PlanItem> items, List<PlanItemTransition> transitions) {
        items.forEach(i -> db.planItems.put(i.id(), i));
        db.transitions.addAll(transitions);
    }

    @Override
    public void update(PlanItem updated, int expectedVersion, PlanItemTransition transition) {
        PlanItem stored = db.planItems.get(updated.id());
        if (stored == null || stored.version() != expectedVersion) {
            throw new ConcurrentModificationException("plan item");
        }
        db.planItems.put(updated.id(), updated);
        db.transitions.add(transition);
    }

    @Override
    public RiskClassPolicy policy() {
        return new RiskClassPolicy(Map.of(
                RiskClass.CRITICAL, new BigDecimal("0.8000"), RiskClass.HIGH, new BigDecimal("0.6000"),
                RiskClass.MEDIUM, new BigDecimal("0.3500"), RiskClass.LOW, BigDecimal.ZERO));
    }
}
