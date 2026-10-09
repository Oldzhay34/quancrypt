package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Reads plans and plan items. */
public interface PlanReader {

    Optional<Plan> byScan(UUID scanId);

    PageResult<PlanItem> items(UUID planId, Optional<PlanItemStateCode> state, int page, int size);

    List<PlanItem> allItems(UUID planId);

    Optional<PlanItem> item(UUID itemId);

    /** Plain read of the owning project (item, plan, scan, project), so the project lock can be taken first. */
    Optional<UUID> projectIdOfItem(UUID itemId);
}
