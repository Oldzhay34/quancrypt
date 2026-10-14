package com.quancrypt.analyzer.evaluation;

/**
 * One benchmark test case at file level (P3.2 mapping rule 1): the benchmark's own label says whether the file contains a
 * misuse we would call P0, and the plugin either reported a P0 finding in that file or did not.
 */
public record BenchmarkCase(String id, boolean labelledVulnerable, boolean reportedP0) {
}
