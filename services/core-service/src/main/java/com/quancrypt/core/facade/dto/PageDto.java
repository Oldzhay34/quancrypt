package com.quancrypt.core.facade.dto;

import java.util.List;

/** A page of items (schemas ProjectPage, ScanPage, FindingPage, AuditPage). */
public record PageDto<T>(List<T> items, int page, int size, long totalElements) {

    public PageDto {
        items = items == null ? null : List.copyOf(items);
    }
}

