package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.PageResult;
import java.util.function.Supplier;

/** Turns the domain's argument checks into validation failures. */
final class Guard {

    private Guard() {
    }

    static <T> T valid(Supplier<T> construction) {
        try {
            return construction.get();
        } catch (IllegalArgumentException e) {
            throw Fail.validation(e.getMessage());
        }
    }

    static void page(int page, int size) {
        if (page < 0 || size < 1 || size > PageResult.MAX_SIZE) {
            throw Fail.validation("page must be 0 or more and size 1.." + PageResult.MAX_SIZE);
        }
    }
}
