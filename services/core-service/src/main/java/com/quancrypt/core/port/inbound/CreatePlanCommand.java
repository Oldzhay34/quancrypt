package com.quancrypt.core.port.inbound;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Creates the plan of a completed scan from the risk assessment of every finding. */
public record CreatePlanCommand(UUID scanId, List<PlanItemInput> items, Optional<Idempotency> idempotency, String caller) {

    public CreatePlanCommand {
        items = List.copyOf(items);
    }
}
