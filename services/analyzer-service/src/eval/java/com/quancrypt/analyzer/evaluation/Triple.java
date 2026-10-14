package com.quancrypt.analyzer.evaluation;

/** What the golden comparison matches on: the file, the algorithm family and the usage context (P3.2). */
public record Triple(String file, String algorithmFamily, String usageContext) {

    @Override
    public String toString() {
        return file + " | " + algorithmFamily + " | " + usageContext;
    }
}
