package com.quancrypt.analyzer.evaluation;

import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.LocationKind;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.function.Predicate;

/**
 * Compares the usages a plugin found with the golden inventory on the triple (file, algorithm family, usage context): the
 * recall is the share of expected triples that were found, the precision the share of found triples that were expected.
 * Test code findings are left out of the found side (the golden file treats test code as out of scope). Entries that no
 * Java plugin can produce are left out of the expected side with a reason (D-184).
 */
public final class GoldenComparison {

    /** The result of one comparison. */
    public record Result(Set<Triple> expected, Set<Triple> found, Set<Triple> missing, Set<Triple> unexpected,
            List<String> priorityMismatches, List<String> excluded) {

        public Result {
            expected = Collections.unmodifiableSet(new LinkedHashSet<>(expected));
            found = Collections.unmodifiableSet(new LinkedHashSet<>(found));
            missing = Collections.unmodifiableSet(new LinkedHashSet<>(missing));
            unexpected = Collections.unmodifiableSet(new LinkedHashSet<>(unexpected));
            priorityMismatches = List.copyOf(priorityMismatches);
            excluded = List.copyOf(excluded);
        }

        public double recall() {
            return expected.isEmpty() ? 1.0 : (double) (expected.size() - missing.size()) / expected.size();
        }

        public double precision() {
            return found.isEmpty() ? 1.0 : (double) (found.size() - unexpected.size()) / found.size();
        }
    }

    private GoldenComparison() {
    }

    /** {@code inScope} decides which golden entries a plugin is expected to find; the others are listed as excluded. */
    public static Result compare(List<GoldenEntry> golden, List<CryptoUsage> usages, Predicate<GoldenEntry> inScope) {
        List<String> excluded = new ArrayList<>();
        Set<Triple> expected = new TreeSet<>(ORDER);
        List<GoldenEntry> scoped = new ArrayList<>();
        for (GoldenEntry entry : golden) {
            if (inScope.test(entry)) {
                expected.add(entry.triple());
                scoped.add(entry);
            } else {
                excluded.add(entry.file() + " (" + entry.symbol() + ")");
            }
        }
        List<CryptoUsage> considered = usages.stream().filter(u -> u.evidence().locationKind() != LocationKind.TEST_CODE).toList();
        Set<Triple> found = new TreeSet<>(ORDER);
        for (CryptoUsage usage : considered) {
            found.add(new Triple(usage.evidence().file().value(), usage.algorithm().family().name(), usage.usageContext().name()));
        }
        Set<Triple> missing = new TreeSet<>(ORDER);
        expected.stream().filter(t -> !found.contains(t)).forEach(missing::add);
        Set<Triple> unexpected = new TreeSet<>(ORDER);
        found.stream().filter(t -> !expected.contains(t)).forEach(unexpected::add);
        List<String> mismatches = new ArrayList<>();
        for (GoldenEntry entry : scoped) {
            Triple triple = entry.triple();
            List<CryptoUsage> same = considered.stream().filter(u -> new Triple(u.evidence().file().value(),
                    u.algorithm().family().name(), u.usageContext().name()).equals(triple)).toList();
            boolean agrees = same.isEmpty() || same.stream().anyMatch(u -> u.priority().name().equals(entry.priority()));
            if (!agrees) {
                mismatches.add(triple + " expected " + entry.priority() + " but got " + same.stream().map(u -> u.priority().name()).distinct().toList());
            }
        }
        return new Result(expected, found, missing, unexpected, mismatches, excluded);
    }

    private static final java.util.Comparator<Triple> ORDER = java.util.Comparator.comparing(Triple::file)
            .thenComparing(Triple::algorithmFamily).thenComparing(Triple::usageContext);
}
