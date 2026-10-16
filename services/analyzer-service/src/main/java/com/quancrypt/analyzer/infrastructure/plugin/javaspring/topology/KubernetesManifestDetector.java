package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.SpringConfigReader;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.error.YAMLException;
import org.yaml.snakeyaml.nodes.MappingNode;
import org.yaml.snakeyaml.nodes.Node;
import org.yaml.snakeyaml.nodes.NodeTuple;
import org.yaml.snakeyaml.nodes.ScalarNode;
import org.yaml.snakeyaml.nodes.SequenceNode;

/**
 * A basic Kubernetes manifest reader (D-206): workloads (Deployment, StatefulSet, DaemonSet, Pod) are nodes with the ports of
 * their containers; a Service is another name of the workload its selector matches (or a node of its own); an Ingress is a
 * connection from outside to the Services behind it, encrypted when it lists TLS hosts; a container environment value that is a
 * URL to a Service is a connection from that workload. YAML is only composed into a node tree (nothing is instantiated), with
 * the same limits as the Spring configuration reader. Helm templates and Kustomize overlays are not rendered.
 */
final class KubernetesManifestDetector implements TopologyDetector {

    static final String ID = "topology.kubernetes";
    private static final Set<String> WORKLOADS = Set.of("Deployment", "StatefulSet", "DaemonSet", "Pod");
    private static final Set<String> BROKER_IMAGES = Set.of("mosquitto", "rabbitmq", "kafka", "emqx", "hivemq", "nats", "redpanda", "activemq");
    private static final Set<String> DATABASE_IMAGES = Set.of("postgres", "mysql", "mariadb", "mongo", "redis", "cassandra");

    private record Workload(TNode node, Map<String, String> labels, List<Env> env, RelativePath file) {
    }

    private record Env(String value, int line) {
    }

    private record ServiceDoc(String name, Map<String, String> selector, List<Integer> ports, int line, RelativePath file) {
    }

    private record IngressDoc(boolean tls, List<String> services, List<Integer> lines, RelativePath file) {
    }

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, TopologySink sink) {
        List<Workload> workloads = new ArrayList<>();
        List<ServiceDoc> services = new ArrayList<>();
        List<IngressDoc> ingresses = new ArrayList<>();
        for (ProjectFile file : context.index().files()) {
            if (file.kind() != FileKind.KUBERNETES || file.location() == LocationKind.TEST_CODE) {
                continue;
            }
            context.index().tree().checkpoint();
            for (Node document : documents(context, file)) {
                if (document instanceof MappingNode root) {
                    read(context, file, root, workloads, services, ingresses);
                }
            }
        }
        for (ServiceDoc service : services) {
            context.index().tree().checkpoint();
            Optional<Workload> backing = workloads.stream().filter(w -> !service.selector().isEmpty() && w.labels().entrySet().containsAll(service.selector().entrySet()))
                    .findFirst();
            TNode node;
            if (backing.isPresent()) {
                node = backing.get().node();
                context.registry().alias(node, service.name());
            } else {
                node = context.registry().declare(ProjectPaths.nodeId(service.name()), NodeKind.SERVICE, true);
                node.present = true;
            }
            service.ports().forEach(node.ports::add);
            node.addEvidence(TopologyContext.at(service.file(), service.line(), LocationKind.CONFIG));
        }
        for (Workload workload : workloads) {
            for (Env env : workload.env()) {
                Target.ofUrl(env.value()).filter(t -> t.protocol().isPresent()).ifPresent(target -> sink.edge(RawEdge.of(workload.node().id, target,
                        target.protocol().get(), target.secureScheme(), TopologyContext.at(workload.file(), env.line(), LocationKind.CONFIG))));
            }
        }
        for (IngressDoc ingress : ingresses) {
            for (int i = 0; i < ingress.services().size(); i++) {
                Optional<Target> target = Target.ofName(ingress.services().get(i));
                int line = ingress.lines().get(i);
                target.ifPresent(t -> sink.edge(RawEdge.of(TopologySink.EXTERNAL_CLIENT, t, Protocol.HTTP, ingress.tls(),
                        TopologyContext.at(ingress.file(), line, LocationKind.CONFIG))));
            }
        }
    }

    private static List<Node> documents(TopologyContext context, ProjectFile file) {
        try {
            String text = String.join("\n", context.index().tree().readLines(file.path()));
            if (!SpringConfigReader.isText(text)) {
                return List.of();
            }
            LoaderOptions options = new LoaderOptions();
            options.setMaxAliasesForCollections(20);
            options.setNestingDepthLimit(40);
            options.setCodePointLimit(2_000_000);
            options.setAllowDuplicateKeys(true);
            List<Node> documents = new ArrayList<>();
            for (Node node : new Yaml(options).composeAll(new StringReader(text))) {
                documents.add(node);
                if (documents.size() >= 500) {
                    break;
                }
            }
            return documents;
        } catch (SourceNotFoundException | PathNotAllowedException | YAMLException | StackOverflowError e) {
            return List.of();
        }
    }

    private static void read(TopologyContext context, ProjectFile file, MappingNode root, List<Workload> workloads, List<ServiceDoc> services,
            List<IngressDoc> ingresses) {
        String kind = scalar(root, "kind").orElse("");
        Optional<String> name = path(root, "metadata", "name").flatMap(KubernetesManifestDetector::text);
        if (name.isEmpty()) {
            return;
        }
        int line = path(root, "metadata", "name").map(n -> n.getStartMark().getLine() + 1).orElse(1);
        if (WORKLOADS.contains(kind)) {
            workloads.add(workload(context, file, root, kind, name.get(), line));
        } else if (kind.equals("Service")) {
            services.add(new ServiceDoc(name.get(), strings(path(root, "spec", "selector").orElse(null)), servicePorts(path(root, "spec", "ports").orElse(null)),
                    line, file.path()));
        } else if (kind.equals("Ingress")) {
            ingresses.add(ingress(file, root));
        }
    }

    private static Workload workload(TopologyContext context, ProjectFile file, MappingNode root, String kind, String name, int line) {
        Optional<Node> spec = kind.equals("Pod") ? path(root, "spec") : path(root, "spec", "template", "spec");
        Map<String, String> labels = kind.equals("Pod") ? strings(path(root, "metadata", "labels").orElse(null))
                : strings(path(root, "spec", "template", "metadata", "labels").orElse(null));
        NodeKind nodeKind = NodeKind.SERVICE;
        List<Env> env = new ArrayList<>();
        Set<Integer> ports = new LinkedHashSet<>();
        for (Node container : sequence(spec.flatMap(s -> path(s, "containers")).orElse(null))) {
            String image = scalar(container, "image").orElse("").toLowerCase(Locale.ROOT);
            if (BROKER_IMAGES.stream().anyMatch(image::contains)) {
                nodeKind = NodeKind.BROKER;
            } else if (DATABASE_IMAGES.stream().anyMatch(image::contains)) {
                nodeKind = NodeKind.DATABASE;
            }
            for (Node variable : sequence(path(container, "env").orElse(null))) {
                path(variable, "value").flatMap(KubernetesManifestDetector::text)
                        .ifPresent(value -> env.add(new Env(value, path(variable, "value").get().getStartMark().getLine() + 1)));
            }
            for (Node port : sequence(path(container, "ports").orElse(null))) {
                scalar(port, "containerPort").flatMap(KubernetesManifestDetector::number).ifPresent(ports::add);
            }
        }
        TNode node = context.registry().declare(ProjectPaths.nodeId(name), nodeKind, true);
        node.present = true;
        node.ports.addAll(ports);
        node.addEvidence(TopologyContext.at(file.path(), line, LocationKind.CONFIG));
        return new Workload(node, labels, env, file.path());
    }

    private static IngressDoc ingress(ProjectFile file, MappingNode root) {
        boolean tls = !sequence(path(root, "spec", "tls").orElse(null)).isEmpty();
        List<String> services = new ArrayList<>();
        List<Integer> lines = new ArrayList<>();
        for (Node rule : sequence(path(root, "spec", "rules").orElse(null))) {
            for (Node entry : sequence(path(rule, "http", "paths").orElse(null))) {
                Optional<Node> service = path(entry, "backend", "service", "name");
                service.flatMap(KubernetesManifestDetector::text).ifPresent(name -> {
                    services.add(name);
                    lines.add(service.get().getStartMark().getLine() + 1);
                });
            }
        }
        return new IngressDoc(tls, services, lines, file.path());
    }

    private static List<Integer> servicePorts(Node ports) {
        List<Integer> found = new ArrayList<>();
        for (Node port : sequence(ports)) {
            scalar(port, "port").flatMap(KubernetesManifestDetector::number).ifPresent(found::add);
            scalar(port, "targetPort").flatMap(KubernetesManifestDetector::number).ifPresent(found::add);
        }
        return found;
    }

    private static Optional<Node> path(Node node, String... keys) {
        Node current = node;
        for (String key : keys) {
            if (!(current instanceof MappingNode mapping)) {
                return Optional.empty();
            }
            Node next = null;
            for (NodeTuple tuple : mapping.getValue()) {
                if (tuple.getKeyNode() instanceof ScalarNode k && k.getValue().equals(key)) {
                    next = tuple.getValueNode();
                    break;
                }
            }
            if (next == null) {
                return Optional.empty();
            }
            current = next;
        }
        return Optional.of(current);
    }

    private static Optional<String> scalar(Node node, String key) {
        return path(node, key).flatMap(KubernetesManifestDetector::text);
    }

    private static Optional<String> text(Node node) {
        return node instanceof ScalarNode s ? Optional.of(s.getValue().strip()).filter(v -> !v.isEmpty()) : Optional.empty();
    }

    private static Optional<Integer> number(String text) {
        try {
            int port = Integer.parseInt(text.strip());
            return port > 0 && port <= 65535 ? Optional.of(port) : Optional.empty();
        } catch (NumberFormatException e) {
            return Optional.empty();
        }
    }

    private static List<Node> sequence(Node node) {
        return node instanceof SequenceNode s ? s.getValue() : List.of();
    }

    private static Map<String, String> strings(Node node) {
        Map<String, String> map = new LinkedHashMap<>();
        if (node instanceof MappingNode mapping) {
            for (NodeTuple tuple : mapping.getValue()) {
                if (tuple.getKeyNode() instanceof ScalarNode key && tuple.getValueNode() instanceof ScalarNode value) {
                    map.put(key.getValue(), value.getValue());
                }
            }
        }
        return map;
    }
}
