package com.quancrypt.core.usecase;

import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.UseCaseException;

/** Builds the use case errors the api layer maps to RFC 9457 problems. */
final class Fail {

    private Fail() {
    }

    static UseCaseException problem(ProblemCode code, String detail) {
        return new UseCaseException(code, detail);
    }

    static UseCaseException notFound(String what) {
        return new UseCaseException(ProblemCode.NOT_FOUND, what + " was not found");
    }

    static UseCaseException validation(String detail) {
        return new UseCaseException(ProblemCode.VALIDATION_FAILED, detail);
    }
}
