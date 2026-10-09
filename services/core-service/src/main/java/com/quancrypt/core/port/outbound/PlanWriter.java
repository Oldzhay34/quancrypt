package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemTransition;
import java.util.List;

/** Writes plans and plan items. */
public interface PlanWriter {

    /** Throws PlanAlreadyExistsException when the scan already has a plan. */
    void insert(Plan plan);

    void insertItems(List<PlanItem> items, List<PlanItemTransition> transitions);

    /** Optimistic update with the transition record; throws ConcurrentModificationException on a version mismatch. */
    void update(PlanItem updated, int expectedVersion, PlanItemTransition transition);
}
