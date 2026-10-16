package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

/** Where topology detectors put the connections they see. */
interface TopologySink {

    /** The id of the synthetic node for callers outside the project (published ports, ingress). */
    String EXTERNAL_CLIENT = "external-client";

    void edge(RawEdge edge);
}
