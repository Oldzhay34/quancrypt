package com.quancrypt.core.port.inbound;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Records a batch of at most 500 findings. */
public record RecordFindingsCommand(UUID scanId, List<FindingInput> findings, Optional<Idempotency> idempotency, String caller) {

    public RecordFindingsCommand {
        findings = List.copyOf(findings);
    }
}
