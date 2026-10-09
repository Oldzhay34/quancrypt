package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.JavaVersion;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.domain.policy.EffortPolicy;
import com.quancrypt.core.domain.policy.JdkRequirementPolicy;
import com.quancrypt.core.domain.policy.PriorityClassifier;
import com.quancrypt.core.domain.policy.PriorityPolicy;
import com.quancrypt.core.domain.policy.PriorityVerdict;
import com.quancrypt.core.domain.service.StrategyPlanner;
import com.quancrypt.core.domain.service.StrategyRegistry;
import com.quancrypt.core.domain.service.strategy.DeviceHybridTlsStrategy;
import com.quancrypt.core.domain.service.strategy.FindingFacts;
import com.quancrypt.core.domain.service.strategy.FixWeakClassicStrategy;
import com.quancrypt.core.domain.service.strategy.HybridKexClassicCertStrategy;
import com.quancrypt.core.domain.service.strategy.HybridTlsKexStrategy;
import com.quancrypt.core.domain.service.strategy.JdkUpgradeStrategy;
import com.quancrypt.core.domain.service.strategy.KeepShortLivedTokenStrategy;
import com.quancrypt.core.domain.service.strategy.KemDemEncryptionStrategy;
import com.quancrypt.core.domain.service.strategy.PqSignatureStrategy;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import static org.assertj.core.api.Assertions.assertThat;

class GoldenInventoryTest {

    private static final int GOLDEN_ENTRIES = 53;

    record Entry(String file, String symbol, AlgorithmFamily algorithm, UsageContext usage, Optional<Integer> keySize,
            LocationKind kind, Priority priority, StrategyCode strategy) {

        CryptoUsage cryptoUsage() {
            return new CryptoUsage(algorithm, usage, keySize, kind);
        }

        /** The golden file has no link data; the QBank device links are the field device client and the broker's TLS listener. */
        boolean onDeviceLink() {
            return usage == UsageContext.TLS_KEY_EXCHANGE
                    && (file.startsWith("field-device-sim/") || file.equals("mosquitto/mosquitto.conf"));
        }

        @Override
        public String toString() {
            return file + "#" + symbol + " " + usage;
        }
    }

    static List<Entry> entries() throws IOException {
        Path path = Path.of(System.getProperty("quancrypt.expected.dir"), "crypto_inventory.yaml");
        List<Map<String, String>> raw = new ArrayList<>();
        Map<String, String> current = null;
        for (String line : Files.readAllLines(path)) {
            String text = line.strip();
            if (text.isEmpty() || text.startsWith("#")) {
                continue;
            }
            if (text.startsWith("- file:")) {
                current = new HashMap<>();
                raw.add(current);
                current.put("file", text.substring("- file:".length()).strip());
            } else if (current != null && line.startsWith("    ") && text.contains(":")) {
                int colon = text.indexOf(':');
                current.put(text.substring(0, colon).strip(), text.substring(colon + 1).strip());
            }
        }
        return raw.stream().map(m -> new Entry(
                m.get("file"), m.get("symbol"), AlgorithmFamily.valueOf(m.get("algorithm_family")), UsageContext.valueOf(m.get("usage_context")),
                Optional.ofNullable(m.get("key_size_bits")).filter(v -> !v.equals("null")).map(Integer::parseInt), LocationKind.valueOf(m.get("location_kind")),
                Priority.valueOf(m.get("priority")), StrategyCode.valueOf(m.get("strategy")))).toList();
    }

    static Stream<Entry> goldenEntries() throws IOException {
        return entries().stream();
    }

    private final PriorityClassifier classifier = new PriorityClassifier();
    private final PriorityPolicy policy = new PriorityPolicy(classifier);
    private final StrategyPlanner planner = new StrategyPlanner(
            new StrategyRegistry(List.of(new FixWeakClassicStrategy(), new HybridTlsKexStrategy(), new DeviceHybridTlsStrategy(),
                    new KemDemEncryptionStrategy(), new PqSignatureStrategy(), new KeepShortLivedTokenStrategy(),
                    new HybridKexClassicCertStrategy(), new JdkUpgradeStrategy())),
            new JdkRequirementPolicy(), new EffortPolicy());

    @Test
    void theGoldenInventoryHas53ApprovedEntries() throws IOException {
        assertThat(entries()).hasSize(GOLDEN_ENTRIES);
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("goldenEntries")
    void everyEntryGetsTheExpectedPriority(Entry entry) {
        assertThat(classifier.classify(entry.cryptoUsage())).isEqualTo(new PriorityVerdict.Derived(entry.priority()));
        assertThat(policy.accept(entry.cryptoUsage(), entry.priority())).isEqualTo(entry.priority());
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("goldenEntries")
    void everyEntryGetsTheExpectedStrategyOnQbanksJdk25(Entry entry) {
        FindingFacts facts = new FindingFacts(entry.cryptoUsage(), entry.priority(), entry.onDeviceLink(), 0, Optional.of(new JavaVersion(25)));
        assertThat(planner.plan(facts).code()).isEqualTo(entry.strategy());
    }

    @Test
    void theGoldenStrategyCountsMatchTheInventory() throws IOException {
        Map<StrategyCode, Long> counts = entries().stream().collect(Collectors.groupingBy(Entry::strategy, Collectors.counting()));
        assertThat(counts).containsEntry(StrategyCode.HYBRID_KEX_CLASSIC_CERT, 27L).containsEntry(StrategyCode.HYBRID_TLS_KEX, 11L)
                .containsEntry(StrategyCode.KEEP_SHORT_LIVED_TOKEN, 6L).containsEntry(StrategyCode.FIX_WEAK_CLASSIC, 4L)
                .containsEntry(StrategyCode.KEM_DEM_ENCRYPTION, 3L).containsEntry(StrategyCode.DEVICE_HYBRID_TLS, 2L);
    }
}
