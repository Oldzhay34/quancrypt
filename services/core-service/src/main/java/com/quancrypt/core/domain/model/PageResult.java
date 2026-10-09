package com.quancrypt.core.domain.model;

import java.util.List;

/** One page of a listing; page numbers start at 0 and a page holds at most 200 items. */
public record PageResult<T>(List<T> items, int page, int size, long total) {

    public static final int MAX_SIZE = 200;

    public PageResult {
        if (page < 0 || size < 1 || size > MAX_SIZE || total < 0) {
            throw new IllegalArgumentException("invalid page parameters");
        }
        items = List.copyOf(items);
    }
}
