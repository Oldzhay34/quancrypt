package com.quancrypt.analyzer.port.inbound;

import java.util.List;
import java.util.UUID;

/** The result of one analysis. */
public record AnalysisView(UUID analysisId, String projectType, RuntimeView runtime, List<FindingView> findings, CbomView cbom,
        StatsView stats) {

    public AnalysisView {
        findings = List.copyOf(findings);
    }
}
