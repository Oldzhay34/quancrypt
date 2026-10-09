package com.quancrypt.core.domain.policy;

import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.StrategyCode;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalInt;

/** The Java version a strategy needs: ML-KEM and ML-DSA arrived in JDK 24 (JEP 496, JEP 497); the others need none (D-150). */
public final class JdkRequirementPolicy {

    /** A strategy cannot run on the project's Java version until it is upgraded. */
    public record UnmetRequirement(StrategyCode intended, int requiredMajor) {
    }

    private static final Map<StrategyCode, Integer> REQUIRED_MAJOR = Map.of(
            StrategyCode.KEM_DEM_ENCRYPTION, 24,
            StrategyCode.PQ_SIGNATURE, 24);

    public OptionalInt requiredMajor(StrategyCode strategy) {
        Integer required = REQUIRED_MAJOR.get(strategy);
        return required == null ? OptionalInt.empty() : OptionalInt.of(required);
    }

    /** Empty when the version is met or unknown (an unknown version is treated as met and noted in the plan). */
    public Optional<UnmetRequirement> unmet(StrategyCode strategy, Optional<JavaVersion> projectJava) {
        OptionalInt required = requiredMajor(strategy);
        if (required.isEmpty() || projectJava.isEmpty() || projectJava.get().isAtLeast(required.getAsInt())) {
            return Optional.empty();
        }
        return Optional.of(new UnmetRequirement(strategy, required.getAsInt()));
    }
}
