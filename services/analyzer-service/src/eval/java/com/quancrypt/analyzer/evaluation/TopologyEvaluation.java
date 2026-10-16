package com.quancrypt.analyzer.evaluation;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.GroupFamily;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceEdge;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.infrastructure.filesystem.FileSystemSourceTreeReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugin;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import org.yaml.snakeyaml.Yaml;

/**
 * The QBank topology against the approved golden file {@code reference-system/expected/topology.yaml} (D-123, P3.4): nodes
 * (id and kind), edges (protocol, TLS, mutual TLS), the findings of the certificates the golden file names, and the inferred
 * key exchange. The golden file also records what was measured on a running system (cipher suite, negotiated group, TLS
 * version). Static analysis does not produce those, so they are not compared; the one thing checked is that the group measured
 * with a Java client is among the groups its Java version offers by default. A device node is matched by its host, because the
 * canonical id is the compose service name (D-207).
 */
public final class TopologyEvaluation {

    private static final Map<String, NodeKind> KINDS = Map.of("external_client", NodeKind.EXTERNAL, "gateway", NodeKind.GATEWAY, "service",
            NodeKind.SERVICE, "broker", NodeKind.BROKER, "field_device", NodeKind.DEVICE);
    private static final String MEASURED_WITH_JAVA = "jdk25-probe";

    /** A node of the golden file. */
    public record GoldenNode(String id, NodeKind kind, String analyzerId) {
    }

    /** An edge of the golden file; {@code measuredGroup} is only set where a Java client was measured. */
    public record GoldenEdge(String source, String target, Protocol protocol, boolean tls, boolean mtls, List<String> certificateFiles,
            Optional<String> measuredGroup) {

        public GoldenEdge {
            certificateFiles = List.copyOf(certificateFiles);
        }
    }

    /** The graph, the golden file and every difference between them (all lists are empty when the topology matches). */
    public record Run(ServiceGraph graph, List<GoldenNode> goldenNodes, List<GoldenEdge> goldenEdges, List<String> nodeDifferences,
            List<String> edgeDifferences, List<String> findingGaps, List<String> keyExchangeDifferences) {

        public Run {
            goldenNodes = List.copyOf(goldenNodes);
            goldenEdges = List.copyOf(goldenEdges);
            nodeDifferences = List.copyOf(nodeDifferences);
            edgeDifferences = List.copyOf(edgeDifferences);
            findingGaps = List.copyOf(findingGaps);
            keyExchangeDifferences = List.copyOf(keyExchangeDifferences);
        }

        public boolean matches() {
            return nodeDifferences.isEmpty() && edgeDifferences.isEmpty() && findingGaps.isEmpty() && keyExchangeDifferences.isEmpty();
        }

        public Optional<ServiceEdge> edge(String goldenSource, String goldenTarget) {
            String source = analyzerId(goldenNodes, goldenSource);
            String target = analyzerId(goldenNodes, goldenTarget);
            return graph.edges().stream().filter(e -> e.source().equals(source) && e.target().equals(target)).findFirst();
        }
    }

    private TopologyEvaluation() {
    }

    /** Runs the plugin over the repository view (compose file and reference system) and compares it with the golden file. */
    public static Run run(JavaSpringPlugin plugin, Path referenceSystem, Path expectedDirectory) throws IOException {
        Path reference = referenceSystem.toRealPath();
        if (!Files.isDirectory(reference.resolve("certs/out"))) {
            throw new IllegalStateException("reference-system/certs/out is missing: run 'bash certs/generate.sh' in reference-system first "
                    + "(the golden topology names the generated certificates)");
        }
        Path repository = Objects.requireNonNull(reference.getParent(), "the reference system has a parent directory");
        var tree = new RepositoryView(new AnalysisRoot(repository.toString()), new FileSystemSourceTreeReader().open(new AnalysisRoot(reference.toString())),
                repository.resolve("docker-compose.yml"));
        ServiceGraph graph = plugin.buildTopology(tree);
        return compare(graph, load(expectedDirectory.resolve("topology.yaml")));
    }

    @SuppressWarnings("unchecked")
    private static Loaded load(Path file) throws IOException {
        Map<String, Object> golden = new Yaml().load(Files.readString(file, StandardCharsets.UTF_8));
        List<GoldenNode> nodes = new ArrayList<>();
        for (Map<String, Object> node : (List<Map<String, Object>>) golden.get("nodes")) {
            String id = (String) node.get("id");
            String kind = (String) node.get("kind");
            nodes.add(new GoldenNode(id, KINDS.get(kind), "field_device".equals(kind) ? (String) node.get("host") : id));
        }
        List<GoldenEdge> edges = new ArrayList<>();
        for (Map<String, Object> edge : (List<Map<String, Object>>) golden.get("edges")) {
            Map<String, Object> crypto = (Map<String, Object>) edge.get("crypto");
            List<String> files = new ArrayList<>();
            for (String side : List.of("server_certificate", "client_certificate")) {
                Map<String, Object> certificate = (Map<String, Object>) crypto.get(side);
                if (certificate != null) {
                    files.add("reference-system/" + certificate.get("file"));
                }
            }
            Map<String, Object> negotiated = (Map<String, Object>) crypto.get("negotiated");
            Optional<String> group = MEASURED_WITH_JAVA.equals(negotiated.get("measured_with"))
                    ? Optional.of((String) negotiated.get("key_exchange_group")) : Optional.empty();
            String protocol = (String) edge.get("protocol");
            edges.add(new GoldenEdge((String) edge.get("source"), (String) edge.get("target"), protocol.startsWith("MQTT") ? Protocol.MQTT : Protocol.HTTP,
                    (Boolean) edge.get("tls"), (Boolean) edge.get("mtls"), files, group));
        }
        return new Loaded(nodes, edges);
    }

    private record Loaded(List<GoldenNode> nodes, List<GoldenEdge> edges) {
    }

    private static Run compare(ServiceGraph graph, Loaded golden) {
        List<String> nodeDifferences = new ArrayList<>();
        Map<String, NodeKind> wantedNodes = new TreeMap<>();
        golden.nodes().forEach(n -> wantedNodes.put(n.analyzerId(), n.kind()));
        Map<String, NodeKind> foundNodes = new TreeMap<>();
        graph.nodes().forEach(n -> foundNodes.put(n.id(), n.kind()));
        wantedNodes.forEach((id, kind) -> {
            if (!foundNodes.containsKey(id)) {
                nodeDifferences.add("missing node " + id);
            } else if (foundNodes.get(id) != kind) {
                nodeDifferences.add("node " + id + " is " + foundNodes.get(id) + ", expected " + kind);
            }
        });
        foundNodes.keySet().stream().filter(id -> !wantedNodes.containsKey(id)).forEach(id -> nodeDifferences.add("unexpected node " + id));

        List<String> edgeDifferences = new ArrayList<>();
        List<String> findingGaps = new ArrayList<>();
        List<String> keyExchangeDifferences = new ArrayList<>();
        Map<String, ServiceEdge> found = new TreeMap<>();
        graph.edges().forEach(e -> found.put(e.source() + " -> " + e.target(), e));
        Map<String, GoldenEdge> wanted = new TreeMap<>();
        golden.edges().forEach(e -> wanted.put(analyzerId(golden.nodes(), e.source()) + " -> " + analyzerId(golden.nodes(), e.target()), e));
        wanted.forEach((key, expected) -> {
            ServiceEdge edge = found.get(key);
            if (edge == null) {
                edgeDifferences.add("missing edge " + key);
                return;
            }
            if (edge.protocol() != expected.protocol() || edge.tls() != expected.tls() || edge.mtls() != expected.mtls()) {
                edgeDifferences.add(String.format(Locale.ROOT, "edge %s is %s tls=%s mtls=%s, expected %s tls=%s mtls=%s", key, edge.protocol(), edge.tls(),
                        edge.mtls(), expected.protocol(), expected.tls(), expected.mtls()));
            }
            List<String> files = edge.findings().stream().map(f -> f.file().value()).toList();
            expected.certificateFiles().stream().filter(f -> !files.contains(f)).forEach(f -> findingGaps.add("edge " + key + " has no finding of " + f));
            keyExchangeDifferences.addAll(keyExchange(key, edge, expected));
        });
        found.keySet().stream().filter(k -> !wanted.containsKey(k)).forEach(k -> edgeDifferences.add("unexpected edge " + k));
        return new Run(graph, golden.nodes(), golden.edges(), nodeDifferences, edgeDifferences, findingGaps, keyExchangeDifferences);
    }

    private static List<String> keyExchange(String key, ServiceEdge edge, GoldenEdge expected) {
        List<String> differences = new ArrayList<>();
        if (expected.measuredGroup().isEmpty()) {
            if (edge.keyExchange().isPresent()) {
                differences.add("edge " + key + " has a key exchange although its client is not a Java client of the project");
            }
            return differences;
        }
        if (edge.keyExchange().isEmpty()) {
            differences.add("edge " + key + " has no key exchange");
            return differences;
        }
        var exchange = edge.keyExchange().get();
        if (!exchange.inferred() || exchange.confidence() >= 1.0) {
            differences.add("edge " + key + " key exchange is not marked as inferred");
        }
        if (exchange.groupFamily() != GroupFamily.CLASSICAL) {
            differences.add("edge " + key + " key exchange is " + exchange.groupFamily() + ", the measured group " + expected.measuredGroup().get()
                    + " is classical");
        }
        if (!exchange.groups().contains(expected.measuredGroup().get())) {
            differences.add("edge " + key + " offers " + exchange.groups() + " but " + expected.measuredGroup().get() + " was measured");
        }
        return differences;
    }

    private static String analyzerId(List<GoldenNode> nodes, String goldenId) {
        return nodes.stream().filter(n -> n.id().equals(goldenId)).map(GoldenNode::analyzerId).findFirst().orElse(goldenId);
    }

    /** The Markdown section of the report. */
    public static String render(Run run) {
        StringBuilder out = new StringBuilder();
        out.append("## 6. Topoloji (P3.4, H2)\n\n");
        out.append("QBank topolojisi `reference-system/expected/topology.yaml` ile karşılaştırılır (D-123). Girdi: kök `docker-compose.yml` ve ")
                .append("`reference-system/` (D-209); cihaz düğümü `host` alanıyla eşlenir (D-207). Ölçülmüş alanlar (şifre takımı, pazarlık edilen grup, ")
                .append("TLS sürümü) statik analizle çıkmaz ve karşılaştırılmaz; tek denetim, Java istemcisiyle ölçülen grubun Java sürümünün varsayılan ")
                .append("gruplarından biri olmasıdır.\n\n");
        out.append("| Ölçüt | Değer | Durum |\n|---|---|---|\n");
        out.append(String.format(Locale.ROOT, "| Düğümler | %d bulundu, %d bekleniyordu | %s |%n", run.graph().nodes().size(), run.goldenNodes().size(),
                run.nodeDifferences().isEmpty() ? "Karşılandı" : "Karşılanmadı"));
        out.append(String.format(Locale.ROOT, "| Kenarlar (protokol, TLS, mTLS) | %d bulundu, %d bekleniyordu | %s |%n", run.graph().edges().size(),
                run.goldenEdges().size(), run.edgeDifferences().isEmpty() ? "Karşılandı" : "Karşılanmadı"));
        out.append("| Kenar–sertifika bulgusu | altın dosyadaki her sertifika | ").append(run.findingGaps().isEmpty() ? "Karşılandı" : "Karşılanmadı")
                .append(" |\n");
        out.append("| Anahtar değişimi çıkarımı | Java istemcili kenarlarda `inferred=true` ve güven < 1 | ")
                .append(run.keyExchangeDifferences().isEmpty() ? "Karşılandı" : "Karşılanmadı").append(" |\n\n");
        for (String difference : concat(run)) {
            out.append("- ").append(difference).append('\n');
        }
        out.append("\n### Kenarlar\n\n| Kaynak | Hedef | Protokol | TLS | mTLS | Bulgu | Anahtar değişimi |\n|---|---|---|---|---|---|---|\n");
        for (ServiceEdge edge : run.graph().edges()) {
            String exchange = edge.keyExchange().map(k -> k.groupFamily() + (k.groups().isEmpty() ? "" : " " + String.join(",", k.groups()))
                    + " (çıkarım, güven " + k.confidence() + ")").orElse("-");
            out.append(String.format(Locale.ROOT, "| %s | %s | %s | %s | %s | %d | %s |%n", edge.source(), edge.target(), edge.protocol(), edge.tls(),
                    edge.mtls(), edge.findings().size(), exchange));
        }
        out.append("\nJDK 25 için grup listesi OpenJDK `jdk-25.0.4-ga` kaynağından (`sun/security/ssl/NamedGroup.java`) okundu; JDK 25'in sonraki ")
                .append("güncellemeleri farklı olabilir ve proje yalnızca özellik sürümünü söylediği için güven 0,5'tir (D-210, D-213).\n");
        return out.toString();
    }

    private static List<String> concat(Run run) {
        List<String> all = new ArrayList<>(run.nodeDifferences());
        all.addAll(run.edgeDifferences());
        all.addAll(run.findingGaps());
        all.addAll(run.keyExchangeDifferences());
        return all;
    }
}
