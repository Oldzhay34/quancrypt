package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.CallerKind;
import java.util.Optional;

/** Parses coded strings of commands into domain enums; an unknown code is a validation failure. */
final class Codes {

    private Codes() {
    }

    static <E extends Enum<E>> E parse(Class<E> type, String value, String field) {
        if (value == null) {
            throw Fail.validation(field + " is required");
        }
        try {
            return Enum.valueOf(type, value);
        } catch (IllegalArgumentException e) {
            throw Fail.validation(field + " is not a known code");
        }
    }

    static <E extends Enum<E>> Optional<E> parseOptional(Class<E> type, Optional<String> value, String field) {
        return value.map(v -> parse(type, v, field));
    }

    static CallerKind caller(String value) {
        return parse(CallerKind.class, value, "caller");
    }
}
