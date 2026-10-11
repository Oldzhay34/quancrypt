package com.quancrypt.core.facade.dto;

import java.util.List;

/** Plan with a page of its items (schema PlanPage). */
public record PlanPageDto(PlanDto plan, List<PlanItemDto> items, int page, int size, long totalElements) {

    public PlanPageDto {
        items = items == null ? null : List.copyOf(items);
    }
}

