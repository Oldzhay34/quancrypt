package com.quancrypt.analyzer.evaluation;

/** One record of reference-system/expected/crypto_inventory.yaml (approved in D-123). */
public record GoldenEntry(String file, String symbol, String algorithmFamily, String usageContext, String locationKind, String priority) {

    public Triple triple() {
        return new Triple(file, algorithmFamily, usageContext);
    }
}
