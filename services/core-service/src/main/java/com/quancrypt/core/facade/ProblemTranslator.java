package com.quancrypt.core.facade;

import com.quancrypt.core.facade.error.ApiProblemException;
import com.quancrypt.core.facade.error.ProblemKind;
import com.quancrypt.core.port.inbound.UseCaseException;
import java.util.function.Supplier;

/** Runs a use case call and turns its UseCaseException into the facade's ApiProblemException (the api layer never sees ports). */
final class ProblemTranslator {

    private ProblemTranslator() {
    }

    static <T> T call(Supplier<T> useCase) {
        try {
            return useCase.get();
        } catch (UseCaseException e) {
            throw new ApiProblemException(ProblemKind.valueOf(e.problem().name()), e.getMessage());
        }
    }

    static void run(Runnable useCase) {
        call(() -> {
            useCase.run();
            return null;
        });
    }
}
