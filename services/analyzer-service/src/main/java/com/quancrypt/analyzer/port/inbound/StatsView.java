package com.quancrypt.analyzer.port.inbound;

/** Counters of one analysis. */
public record StatsView(int filesScanned, int findingsTotal, long durationMs) {
}
