package com.quancrypt.core.domain.service.strategy;

import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.policy.JdkRequirementPolicy.UnmetRequirement;
import java.util.Optional;

/** Everything a strategy may look at when it decides whether it supports a finding. */
public record FindingFacts(
        CryptoUsage usage,
        Priority priority,
        boolean onDeviceLink,
        int callSiteCount,
        Optional<JavaVersion> javaVersion,
        Optional<UnmetRequirement> pendingUpgrade) {

    public FindingFacts(CryptoUsage usage, Priority priority, boolean onDeviceLink, int callSiteCount, Optional<JavaVersion> javaVersion) {
        this(usage, priority, onDeviceLink, callSiteCount, javaVersion, Optional.empty());
    }

    public FindingFacts withPendingUpgrade(UnmetRequirement unmet) {
        return new FindingFacts(usage, priority, onDeviceLink, callSiteCount, javaVersion, Optional.of(unmet));
    }
}
