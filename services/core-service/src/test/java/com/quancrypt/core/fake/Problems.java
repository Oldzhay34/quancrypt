package com.quancrypt.core.fake;

import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.UseCaseException;
import org.assertj.core.api.ThrowableAssert.ThrowingCallable;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** Asserts that a use case fails with a given problem code. */
public final class Problems {

    private Problems() {
    }

    public static void assertProblem(ThrowingCallable call, ProblemCode code) {
        assertThatThrownBy(call).isInstanceOfSatisfying(UseCaseException.class, e -> assertThat(e.problem()).isEqualTo(code));
    }
}
