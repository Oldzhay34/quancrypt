package com.quancrypt.core.facade.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** Body of RecordFindings (schema FindingBatch). */
public record FindingBatchInput(@NotNull @Size(max = 500) List<@NotNull @Valid FindingInputDto> findings) {

    public FindingBatchInput {
        findings = findings == null ? null : List.copyOf(findings);
    }
}

