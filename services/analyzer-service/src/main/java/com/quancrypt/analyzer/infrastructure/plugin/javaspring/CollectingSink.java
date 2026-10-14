package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

/** Collects what detectors report for one analysis. Not shared between analyses. */
final class CollectingSink implements DetectionSink {

    private static final int MAX_UNRESOLVED = 200;
    /** Far above the 5000 findings one analysis may return; a project beyond it is a reading limit (D-181). */
    static final int MAX_OBSERVATIONS = 50_000;

    private final List<Observation> observations = new ArrayList<>();
    private final List<LibraryDependency> libraries = new ArrayList<>();
    private final Set<String> unresolved = new TreeSet<>();

    @Override
    public void add(Observation observation) {
        if (observations.size() >= MAX_OBSERVATIONS) {
            throw new SourceTooLargeException("the project has more crypto usages than one analysis can hold");
        }
        observations.add(observation);
    }

    @Override
    public void library(LibraryDependency dependency) {
        libraries.add(dependency);
    }

    @Override
    public void unresolved(String detectorId, String rawName) {
        if (unresolved.size() < MAX_UNRESOLVED) {
            unresolved.add(detectorId + ": " + NameSanitizer.clean(rawName));
        }
    }

    List<Observation> observations() {
        return observations;
    }

    List<LibraryDependency> libraries() {
        return libraries;
    }

    Set<String> unresolved() {
        return unresolved;
    }
}
