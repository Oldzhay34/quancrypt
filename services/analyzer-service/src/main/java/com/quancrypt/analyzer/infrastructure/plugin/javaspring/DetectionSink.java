package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

/** Where detectors put what they find, so a detector never needs to know how results are collected. */
public interface DetectionSink {

    void add(Observation observation);

    void library(LibraryDependency dependency);

    /** A raw name the canonical dictionary does not know (reported in the evaluation, never silently dropped). */
    void unresolved(String detectorId, String rawName);
}
