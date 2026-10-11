package com.quancrypt.core.facade.dto;

import java.util.List;

/** Consents of a project (schema ConsentList). */
public record ConsentListDto(List<ConsentDto> items) {

    public ConsentListDto {
        items = items == null ? null : List.copyOf(items);
    }
}

