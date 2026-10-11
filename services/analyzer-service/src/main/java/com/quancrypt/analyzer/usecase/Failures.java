package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.exception.UnsupportedProjectException;
import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import java.util.function.Supplier;

/**
 * Translates the domain failures of a use case step into contract problem codes. Any other exception (a plugin or
 * adapter defect) is left alone and becomes an internal error.
 */
final class Failures {

    private Failures() {
    }

    static <T> T translate(Supplier<T> step) {
        try {
            return step.get();
        } catch (PathNotAllowedException e) {
            throw new AnalyzerUseCaseException(ProblemCode.PATH_NOT_ALLOWED, e.getMessage());
        } catch (SourceNotFoundException e) {
            throw new AnalyzerUseCaseException(ProblemCode.NOT_FOUND, e.getMessage());
        } catch (SourceTooLargeException e) {
            // Reading limits are reported as an unsupported project (D-181).
            throw new AnalyzerUseCaseException(ProblemCode.UNSUPPORTED_PROJECT, e.getMessage());
        } catch (UnsupportedProjectException e) {
            throw new AnalyzerUseCaseException(ProblemCode.UNSUPPORTED_PROJECT, e.getMessage());
        }
    }
}
