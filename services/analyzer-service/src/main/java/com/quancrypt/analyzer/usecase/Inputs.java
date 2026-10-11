package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.Snippet;
import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import com.quancrypt.analyzer.port.inbound.ProblemCode;

/** Turns the caller's raw input into domain values; a refusal is an AnalyzerUseCaseException. */
final class Inputs {

    private Inputs() {
    }

    static AnalysisRoot root(AllowedRoots allowed, String root) {
        try {
            return allowed.admit(root);
        } catch (PathNotAllowedException e) {
            throw new AnalyzerUseCaseException(ProblemCode.PATH_NOT_ALLOWED, e.getMessage());
        }
    }

    static RelativePath path(String path) {
        if (path == null) {
            throw new AnalyzerUseCaseException(ProblemCode.VALIDATION_FAILED, "the path is missing");
        }
        try {
            return RelativePath.of(path);
        } catch (PathNotAllowedException e) {
            throw new AnalyzerUseCaseException(ProblemCode.PATH_NOT_ALLOWED, e.getMessage());
        }
    }

    static int line(int line) {
        if (line < 1) {
            throw new AnalyzerUseCaseException(ProblemCode.VALIDATION_FAILED, "the line must be at least 1");
        }
        return line;
    }

    static int context(int context) {
        if (context < 0 || context > Snippet.MAX_CONTEXT) {
            throw new AnalyzerUseCaseException(ProblemCode.VALIDATION_FAILED, "the context must be 0 to 10 lines");
        }
        return context;
    }
}
