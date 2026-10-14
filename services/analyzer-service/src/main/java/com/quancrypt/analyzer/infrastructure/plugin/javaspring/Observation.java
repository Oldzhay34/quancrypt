package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.Objects;
import java.util.Optional;

/**
 * What a detector saw: a draft of a crypto usage without its priority. {@code usageFromLoader} marks a key file whose
 * usage context is derived later from the code that loads it (D-185); {@code priorityOverride} is the priority the
 * detector itself stands for when the table has no answer (D-188).
 */
public record Observation(Role role, Evidence evidence, String symbol, CryptoAlgorithm algorithm, UsageContext usage,
        Optional<String> library, double confidence, String detectorId, Optional<Priority> priorityOverride, boolean usageFromLoader) {

    public Observation {
        Objects.requireNonNull(role, "role");
        Objects.requireNonNull(evidence, "evidence");
        Objects.requireNonNull(symbol, "symbol");
        Objects.requireNonNull(algorithm, "algorithm");
        Objects.requireNonNull(usage, "usage");
        Objects.requireNonNull(library, "library");
        Objects.requireNonNull(detectorId, "detectorId");
        Objects.requireNonNull(priorityOverride, "priorityOverride");
    }

    public static Observation finding(Evidence evidence, String symbol, CryptoAlgorithm algorithm, UsageContext usage, double confidence,
            String detectorId, String library) {
        return new Observation(Role.FINDING, evidence, symbol, algorithm, usage, Optional.ofNullable(library), confidence, detectorId,
                Optional.empty(), false);
    }

    public Observation withRole(Role newRole) {
        return new Observation(newRole, evidence, symbol, algorithm, usage, library, confidence, detectorId, priorityOverride,
                usageFromLoader);
    }

    public Observation withPriority(Priority priority) {
        return new Observation(role, evidence, symbol, algorithm, usage, library, confidence, detectorId, Optional.of(priority),
                usageFromLoader);
    }

    public Observation fromLoader() {
        return new Observation(role, evidence, symbol, algorithm, usage, library, confidence, detectorId, priorityOverride, true);
    }

    public Observation withUsage(UsageContext newUsage) {
        return new Observation(role, evidence, symbol, algorithm, newUsage, library, confidence, detectorId, priorityOverride,
                usageFromLoader);
    }

    public Observation withAlgorithm(CryptoAlgorithm newAlgorithm) {
        return new Observation(role, evidence, symbol, newAlgorithm, usage, library, confidence, detectorId, priorityOverride,
                usageFromLoader);
    }

    public Observation withConfidence(double newConfidence) {
        return new Observation(role, evidence, symbol, algorithm, usage, library, newConfidence, detectorId, priorityOverride,
                usageFromLoader);
    }
}
