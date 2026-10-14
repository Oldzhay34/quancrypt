package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

/**
 * One detector: it reads the project files it applies to and reports what it sees to the sink. Every detector is one
 * class with a fixed id; a new detector is a new class added to the plugin's list (OCP).
 */
public interface CryptoDetector {

    /** The fixed detector id, lower case with dots and hyphens (finding.schema.json {@code detector_id}). */
    String detectorId();

    boolean appliesTo(ProjectFile file);

    void detect(ProjectIndex index, FileContext context, DetectionSink sink);
}
