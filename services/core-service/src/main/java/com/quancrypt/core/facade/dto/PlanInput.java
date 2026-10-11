package com.quancrypt.core.facade.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** Body of CreatePlan (schema PlanInput). */
public record PlanInput(@NotNull @Size(max = 500) List<@NotNull @Valid PlanItemInputDto> items) {

    public PlanInput {
        items = items == null ? null : List.copyOf(items);
    }
}

