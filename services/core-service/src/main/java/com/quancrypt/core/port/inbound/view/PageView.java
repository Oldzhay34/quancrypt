package com.quancrypt.core.port.inbound.view;

import java.util.List;

/** One page of a listing (at most 200 items). */
public record PageView<T>(List<T> items, int page, int size, long total) {

    public PageView {
        items = List.copyOf(items);
    }
}
