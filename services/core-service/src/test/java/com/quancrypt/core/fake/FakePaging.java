package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.PageResult;
import java.util.List;

/** Slices a list into a page the way the real readers do. */
final class FakePaging {

    private FakePaging() {
    }

    static <T> PageResult<T> slice(List<T> all, int page, int size) {
        int from = Math.min(all.size(), page * size);
        int to = Math.min(all.size(), from + size);
        return new PageResult<>(all.subList(from, to), page, size, all.size());
    }
}
