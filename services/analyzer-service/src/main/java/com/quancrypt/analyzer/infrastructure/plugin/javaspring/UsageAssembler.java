package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.domain.policy.PriorityClassifier;
import com.quancrypt.analyzer.domain.policy.PriorityVerdict;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;
import java.util.function.UnaryOperator;

/**
 * Turns the detectors' observations into crypto usages: fallback observations stay only when the file has no finding of
 * the family, key sizes the code cannot show are taken from supporting observations and from loader links, key files get
 * the usage the loader decides (D-185), and the priority table decides what stays: usages that need no migration are
 * dropped (core-service would reject them, D-186) and usages the table cannot place carry the detector's own priority.
 */
final class UsageAssembler {

    /**
     * The priority of a usage whose algorithm or context is unknown and whose detector named none (D-241): the context
     * column of the crypto-domain table where it decides alone (TLS key exchange P1; certificates and TLS or mTLS
     * authentication P3), medium (P2) otherwise. core-service plans those contexts only at these priorities.
     */
    static final Priority UNDETERMINED_DEFAULT = Priority.P2;

    private static final Set<UsageContext> IDENTITY_CONTEXTS = Set.of(UsageContext.CERTIFICATE, UsageContext.TLS_SERVER_AUTH,
            UsageContext.MTLS_CLIENT_AUTH);

    private static final Set<AlgorithmFamily> SIZED = Set.of(AlgorithmFamily.RSA, AlgorithmFamily.ECDSA, AlgorithmFamily.DH,
            AlgorithmFamily.DSA, AlgorithmFamily.ECDH);

    private final PriorityClassifier classifier;
    private final UnaryOperator<String> sanitizer;

    UsageAssembler(PriorityClassifier classifier) {
        this(classifier, UnaryOperator.identity());
    }

    /**
     * The sanitizer sees the two texts a finding copies from the project, the raw name of an unknown algorithm and the symbol, and returns them
     * unchanged or replaced by a label (security review P3.3: a literal that is a secret must not become a name).
     */
    UsageAssembler(PriorityClassifier classifier, UnaryOperator<String> sanitizer) {
        this.classifier = classifier;
        this.sanitizer = sanitizer;
    }

    List<CryptoUsage> assemble(List<Observation> observations, KeyFileLinker.Linking linking) {
        Set<String> findingKeys = new HashSet<>();
        observations.stream().filter(o -> o.role() == Role.FINDING).forEach(o -> findingKeys.add(familyKey(o)));
        Map<String, Set<Integer>> supportedSizes = new HashMap<>();
        observations.stream().filter(o -> o.role() != Role.FINDING || o.usage() == UsageContext.UNKNOWN).forEach(o -> o.algorithm().keySizeBits()
                .ifPresent(size -> supportedSizes.computeIfAbsent(familyKey(o), k -> new TreeSet<>()).add(size)));

        Map<String, CryptoUsage> unique = new LinkedHashMap<>();
        for (Observation observation : observations) {
            boolean reported = observation.role() == Role.FINDING
                    || (observation.role() == Role.FALLBACK && !findingKeys.contains(familyKey(observation)));
            if (!reported) {
                continue;
            }
            Observation complete = withLoaderUsage(withKeySize(observation, supportedSizes, linking), linking);
            toUsage(complete).ifPresent(usage -> unique.merge(identity(usage), usage,
                    (a, b) -> a.confidence() >= b.confidence() ? a : b));
        }
        return unique.values().stream().sorted(ORDER).toList();
    }

    private Observation withKeySize(Observation observation, Map<String, Set<Integer>> supportedSizes, KeyFileLinker.Linking linking) {
        CryptoAlgorithm algorithm = observation.algorithm();
        if (algorithm.keySizeBits().isPresent() || !SIZED.contains(algorithm.family())) {
            return observation;
        }
        Set<Integer> sizes = supportedSizes.getOrDefault(familyKey(observation), Set.of());
        Optional<Integer> size = sizes.size() == 1 ? Optional.of(sizes.iterator().next()) : Optional.empty();
        size = size.or(() -> linking.keySizeFor(observation.evidence().file(), algorithm.family()));
        return size.map(s -> observation.withAlgorithm(new CryptoAlgorithm(algorithm.family(), algorithm.rawName(), algorithm.mode(),
                algorithm.padding(), algorithm.hash(), Optional.of(s)))).orElse(observation);
    }

    private Observation withLoaderUsage(Observation observation, KeyFileLinker.Linking linking) {
        if (!observation.usageFromLoader()) {
            return observation;
        }
        return linking.usageOf(observation.evidence().file())
                .map(usage -> observation.withUsage(usage).withConfidence(0.6))
                .orElse(observation.withConfidence(0.3));
    }

    private Optional<CryptoUsage> toUsage(Observation observation) {
        CryptoAlgorithm named = observation.algorithm();
        // A known family got its raw name through the dictionary; only an unknown one is text copied from the project.
        String rawName = named.family() == AlgorithmFamily.UNKNOWN ? sanitizer.apply(named.rawName()) : named.rawName();
        CryptoAlgorithm algorithm = new CryptoAlgorithm(named.family(), rawName, named.mode(), named.padding(), named.hash(),
                named.keySizeBits());
        CryptoUsage draft = new CryptoUsage(observation.evidence(), sanitizer.apply(observation.symbol()), algorithm, observation.usage(),
                Priority.P3, observation.library(), observation.confidence(), observation.detectorId());
        PriorityVerdict verdict = classifier.classify(draft);
        Priority priority;
        if (verdict instanceof PriorityVerdict.Derived derived) {
            priority = derived.priority();
        } else if (verdict instanceof PriorityVerdict.Undetermined) {
            priority = observation.priorityOverride().orElse(undeterminedDefault(observation.usage()));
        } else {
            return Optional.empty();
        }
        return Optional.of(new CryptoUsage(draft.evidence(), draft.symbol(), draft.algorithm(), draft.usageContext(), priority,
                draft.library(), draft.confidence(), draft.detectorId()));
    }

    static Priority undeterminedDefault(UsageContext context) {
        if (context == UsageContext.TLS_KEY_EXCHANGE) {
            return Priority.P1;
        }
        return IDENTITY_CONTEXTS.contains(context) ? Priority.P3 : UNDETERMINED_DEFAULT;
    }

    private static String familyKey(Observation observation) {
        return observation.evidence().file().value() + "|" + observation.algorithm().family();
    }

    private static String identity(CryptoUsage usage) {
        CryptoAlgorithm a = usage.algorithm();
        return String.join("|", usage.evidence().file().value(), usage.symbol(), a.family().name(), usage.usageContext().name(),
                a.mode().orElse(""), a.padding().orElse(""), a.hash().orElse(""), a.keySizeBits().map(String::valueOf).orElse(""),
                a.rawName());
    }

    private static final Comparator<CryptoUsage> ORDER = Comparator
            .comparing((CryptoUsage u) -> u.evidence().file().value())
            .thenComparingInt(u -> u.evidence().lines().map(l -> l.start()).orElse(0))
            .thenComparing(u -> u.algorithm().family().name())
            .thenComparing(u -> u.usageContext().name())
            .thenComparing(CryptoUsage::detectorId)
            .thenComparing(CryptoUsage::symbol);
}
