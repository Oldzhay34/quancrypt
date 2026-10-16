package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemFacts;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemRole;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * MQTT in the project: the listeners of a Mosquitto configuration (the broker node, its port, whether it has a certificate and
 * asks for client certificates), the Paho clients in Java code (broker URI and the topics they subscribe to or publish on, seen
 * as evidence), and devices described only by compose: a service without a Spring module that depends on a broker node and mounts a
 * certificate with its private key is a device that connects to the broker as a client (D-211).
 */
final class MqttTopologyDetector implements TopologyDetector, UnitTopologyDetector {

    static final String ID = "topology.mqtt";
    private static final Set<String> CLIENT_TYPES = Set.of("MqttClient", "MqttAsyncClient");
    private static final Set<String> TOPIC_CALLS = Set.of("subscribe", "publish");
    private static final Pattern LISTENER = Pattern.compile("^listener\\s+(\\d{1,5})(?:\\s.*)?$");

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, TopologySink sink) {
        brokers(context);
        devices(context, sink);
    }

    private static void brokers(TopologyContext context) {
        for (ProjectFile file : context.index().files()) {
            if (file.kind() != FileKind.MOSQUITTO_CONF || file.location() == LocationKind.TEST_CODE) {
                continue;
            }
            List<String> lines;
            try {
                lines = context.index().lines(file.path());
            } catch (SourceNotFoundException | PathNotAllowedException e) {
                continue;
            }
            TNode node = brokerNode(context, file);
            node.kind = NodeKind.BROKER;
            node.present = true;
            for (Map.Entry<Integer, Section> entry : sections(file, lines).entrySet()) {
                Section section = entry.getValue();
                if (entry.getKey() > 0) {
                    node.ports.add(entry.getKey());
                }
                section.evidence.forEach(node::addEvidence);
                node.listeners.put(entry.getKey(), new Listener(section.certificate.isPresent(),
                        section.certificate.isPresent() && section.requiresClientCertificate, section.certificate.map(List::of).orElse(List.of()),
                        Optional.empty(), section.evidence));
            }
        }
    }

    /** The settings of one {@code listener} line (key 0: the default listener, settings before the first line). */
    private static final class Section {
        Optional<String> certificate = Optional.empty();
        boolean requiresClientCertificate;
        final List<Evidence> evidence = new ArrayList<>();
    }

    /** A Mosquitto configuration split by listener: a setting belongs to the nearest {@code listener} line above it. */
    private static Map<Integer, Section> sections(ProjectFile file, List<String> lines) {
        Map<Integer, Section> sections = new TreeMap<>();
        int current = 0;
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i).strip();
            String[] parts = line.split("\\s+", 2);
            if (line.isEmpty() || line.startsWith("#") || parts.length < 2) {
                continue;
            }
            Matcher listener = LISTENER.matcher(line);
            if (listener.matches()) {
                int port = Integer.parseInt(listener.group(1));
                current = port > 0 && port <= 65535 ? port : 0;
                if (current > 0) {
                    sections.computeIfAbsent(current, k -> new Section()).evidence.add(TopologyContext.at(file.path(), i + 1, LocationKind.CONFIG));
                }
            } else if (parts[0].equals("certfile")) {
                Section section = sections.computeIfAbsent(current, k -> new Section());
                section.certificate = Optional.of(parts[1].strip());
                section.evidence.add(TopologyContext.at(file.path(), i + 1, LocationKind.CONFIG));
            } else if (parts[0].equals("require_certificate") && parts[1].strip().equalsIgnoreCase("true")) {
                Section section = sections.computeIfAbsent(current, k -> new Section());
                section.requiresClientCertificate = true;
                section.evidence.add(TopologyContext.at(file.path(), i + 1, LocationKind.CONFIG));
            }
        }
        return sections;
    }

    /** The compose service that mounts this configuration file, else the node named like its directory, else a new broker node. */
    private static TNode brokerNode(TopologyContext context, ProjectFile file) {
        String path = file.path().value();
        for (ComposeService service : context.compose()) {
            if (service.volumes().stream().anyMatch(m -> m.hostPath().filter(path::equals).isPresent())) {
                Optional<TNode> mounted = context.registry().byName(service.name());
                if (mounted.isPresent()) {
                    return mounted.get();
                }
            }
        }
        String directory = ProjectPaths.directoryOf(path);
        String name = directory.isEmpty() ? "mosquitto" : ProjectPaths.baseName(directory);
        return context.registry().byName(name).orElseGet(() -> context.registry().declare(ProjectPaths.nodeId(name), NodeKind.BROKER, true));
    }

    /** The Paho clients of one Java file: the broker URI of every {@code new MqttClient(..)}, the topics as evidence. */
    @Override
    public void detect(TopologyContext context, JavaUnit unit, TopologySink sink) {
        if (!unit.importsPackage("org.eclipse.paho")) {
            return;
        }
        Module module = context.modules().of(unit.path()).orElse(null);
        TNode node = context.nodeOf(unit.path()).orElse(null);
        if (module == null || node == null) {
            return;
        }
        Set<String> bundles = JavaClients.bundles(unit);
        List<Node> topics = new ArrayList<>();
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            if (TOPIC_CALLS.contains(call.getNameAsString())) {
                topics.add(call);
            }
        }
        for (ObjectCreationExpr creation : unit.findAll(ObjectCreationExpr.class)) {
            if (!CLIENT_TYPES.contains(creation.getType().getNameAsString()) || creation.getArguments().isEmpty()) {
                continue;
            }
            Optional<Target> target = brokerTarget(unit, module, creation.getArgument(0));
            if (target.isEmpty()) {
                continue;
            }
            List<Node> seen = new ArrayList<>();
            seen.add(creation);
            seen.addAll(topics);
            sink.edge(new RawEdge(node.id, target.get(), Protocol.MQTT, target.get().secureScheme(), JavaClients.evidence(unit, seen), bundles, Set.of()));
        }
    }

    private static Optional<Target> brokerTarget(JavaUnit unit, Module module, Expression argument) {
        Optional<Target> literal = unit.string(argument).flatMap(Target::ofUrl);
        if (literal.isPresent()) {
            return literal;
        }
        String name = argument instanceof MethodCallExpr call ? call.getNameAsString()
                : argument instanceof NameExpr n ? n.getNameAsString() : argument instanceof FieldAccessExpr f ? f.getNameAsString() : "";
        if (name.isEmpty()) {
            return Optional.empty();
        }
        String wanted = ConfigUrls.relaxed(name.startsWith("get") && name.length() > 3 ? name.substring(3) : name);
        for (ConfigUrls.UrlProperty url : ConfigUrls.of(module)) {
            if (url.protocol() == Protocol.MQTT && ConfigUrls.relaxed(ConfigUrls.lastSegment(url.property().key())).equals(wanted)) {
                return Optional.of(url.target());
            }
        }
        return Optional.empty();
    }

    private static void devices(TopologyContext context, TopologySink sink) {
        for (ComposeService service : context.compose()) {
            Optional<TNode> node = context.registry().byName(service.name());
            if (node.isEmpty() || !node.get().present || node.get().module.isPresent() || node.get().kind == NodeKind.BROKER
                    || node.get().kind == NodeKind.DATABASE) {
                continue;
            }
            Set<String> identity = new LinkedHashSet<>();
            List<Evidence> mounts = new ArrayList<>();
            for (ComposeService.Mount mount : service.volumes()) {
                mount.hostPath().flatMap(path -> certificateOf(context, path)).ifPresent(certificate -> {
                    identity.add(certificate.file().value());
                    mounts.add(TopologyContext.at(service.file(), mount.line(), LocationKind.CONFIG));
                });
            }
            for (ComposeService.Dependency dependency : service.dependsOn()) {
                Optional<TNode> broker = context.registry().byName(dependency.name().toLowerCase(Locale.ROOT)).filter(n -> n.kind == NodeKind.BROKER);
                if (broker.isEmpty()) {
                    continue;
                }
                if (identity.isEmpty()) {
                    continue;
                }
                node.get().kind = NodeKind.DEVICE;
                List<Evidence> evidence = new ArrayList<>();
                evidence.add(TopologyContext.at(service.file(), dependency.line(), LocationKind.CONFIG));
                evidence.addAll(mounts);
                sink.edge(new RawEdge(node.get().id, new Target(broker.get().id.toLowerCase(Locale.ROOT), -1, ""), Protocol.MQTT, false, evidence,
                        Set.of(), identity));
            }
        }
    }

    /** The certificate that belongs to a mounted private key: the identity a device presents. */
    private static Optional<PemFacts> certificateOf(TopologyContext context, String hostPath) {
        try {
            RelativePath path = RelativePath.of(hostPath);
            return context.index().pem().get(path).filter(f -> f.role() == PemRole.PRIVATE_KEY).flatMap(f -> context.index().pem().counterpart(f.file()))
                    .filter(f -> f.role() == PemRole.CERTIFICATE);
        } catch (PathNotAllowedException e) {
            return Optional.empty();
        }
    }
}
