package com.quancrypt.core.domain.policy;

import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.Priority;
import java.util.List;

/** Applies the crypto-domain priority table (P0 to P3) to a crypto usage; first matching rule wins (D-149, D-151). */
public final class PriorityClassifier {

    private record Rule(Specification<CryptoUsage> when, PriorityVerdict verdict) {
    }

    private static PriorityVerdict derived(Priority priority) {
        return new PriorityVerdict.Derived(priority);
    }

    private static final List<Rule> RULES = List.of(
            new Rule(CryptoUsageSpecs.WEAK_CLASSIC, derived(Priority.P0)),
            new Rule(CryptoUsageSpecs.KEYSTORE_ASSET, derived(Priority.P3)),
            new Rule(CryptoUsageSpecs.UNDETERMINED, new PriorityVerdict.Undetermined()),
            new Rule(CryptoUsageSpecs.NEEDS_NO_MIGRATION, new PriorityVerdict.NotApplicable()),
            new Rule(CryptoUsageSpecs.QUANTUM_VULNERABLE.and(CryptoUsageSpecs.TLS_KEY_EXCHANGE), derived(Priority.P1)),
            new Rule(CryptoUsageSpecs.QUANTUM_VULNERABLE.and(CryptoUsageSpecs.KEY_ESTABLISHMENT_USAGE), derived(Priority.P1)),
            new Rule(CryptoUsageSpecs.QUANTUM_VULNERABLE.and(CryptoUsageSpecs.SIGNATURE_USAGE), derived(Priority.P2)),
            new Rule(CryptoUsageSpecs.QUANTUM_VULNERABLE.and(CryptoUsageSpecs.TOKEN_SIGNATURE_USAGE), derived(Priority.P3)),
            new Rule(CryptoUsageSpecs.QUANTUM_VULNERABLE.and(CryptoUsageSpecs.IDENTITY_OR_CERTIFICATE_USAGE), derived(Priority.P3)));

    public PriorityVerdict classify(CryptoUsage usage) {
        return RULES.stream()
                .filter(rule -> rule.when().isSatisfiedBy(usage))
                .map(Rule::verdict)
                .findFirst()
                .orElseGet(PriorityVerdict.Undetermined::new);
    }
}
