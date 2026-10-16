package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;

/**
 * A topology detector that reads one parsed Java file at a time. The builder parses each file that may hold a connection once,
 * hands it to every unit detector and lets it go before the next one: no syntax tree is kept (a tree needs memory in proportion to
 * the file, P3.2), so a project with many such files cannot exhaust the heap.
 */
interface UnitTopologyDetector {

    /** The fixed detector id, lower case with dots and hyphens. */
    String detectorId();

    void detect(TopologyContext context, JavaUnit unit, TopologySink sink);
}
