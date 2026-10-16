package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

/**
 * One topology detector: it reads what it understands (configuration, Java code, compose, manifests), declares facts about
 * nodes in the registry and reports connections to the sink. Every detector is one class with a fixed id; a new one is added
 * to the builder's list (OCP).
 */
interface TopologyDetector {

    /** The fixed detector id, lower case with dots and hyphens. */
    String detectorId();

    void detect(TopologyContext context, TopologySink sink);
}
