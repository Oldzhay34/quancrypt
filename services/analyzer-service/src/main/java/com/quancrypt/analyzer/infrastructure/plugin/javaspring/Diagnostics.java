package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import java.util.List;
import java.util.Set;

/**
 * What the analysis could not do: Java files that could not be parsed, detectors that failed on a file, and raw names the
 * canonical dictionary does not know. Only the evaluation reads it today (see {@link AnalysisOutcome}).
 */
public record Diagnostics(int javaFilesParsed, int javaFilesSkipped, List<String> detectorFailures, Set<String> unresolvedNames) {

    public Diagnostics {
        detectorFailures = List.copyOf(detectorFailures);
        unresolvedNames = Set.copyOf(unresolvedNames);
    }
}
