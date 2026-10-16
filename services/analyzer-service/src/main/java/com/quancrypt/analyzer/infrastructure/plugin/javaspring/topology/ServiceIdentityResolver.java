package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;

/**
 * Decides who the services are and what each is called (D-207): one node per module and per compose service, and a module
 * and a compose service that describe the same service become one node. The compose service name is the canonical id; without
 * compose it is the {@code spring.application.name}, then the directory name. Every other name stays an alias, so a URL host
 * written in any of them reaches the node.
 */
final class ServiceIdentityResolver {

    private static final Set<String> BROKER_IMAGES = Set.of("mosquitto", "rabbitmq", "kafka", "emqx", "hivemq", "nats", "redpanda", "activemq",
            "artemis");
    private static final Set<String> DATABASE_IMAGES = Set.of("postgres", "pgvector", "mysql", "mariadb", "mongo", "redis", "cassandra",
            "mssql", "oracle");

    ServiceRegistry resolve(ProjectIndex index, Modules modules, List<ComposeService> compose) {
        ServiceRegistry registry = new ServiceRegistry();
        List<ComposeService> unmatched = new ArrayList<>(compose);
        for (Module module : modules.all()) {
            Optional<ComposeService> service = compose.stream().filter(c -> describes(c, module)).findFirst();
            service.ifPresent(unmatched::remove);
            String id = service.map(ComposeService::name).map(ProjectPaths::nodeId).orElseGet(() -> ProjectPaths.nodeId(module.name()));
            TNode node = registry.declare(id, module.isGateway() ? NodeKind.GATEWAY : NodeKind.SERVICE, true);
            registry.bind(module, node);
            node.compose = service;
            registry.alias(node, module.name());
            registry.alias(node, module.directoryName());
            Module.Server server = module.server();
            node.ports.add(server.port());
            node.listener = listener(index, module, server);
            module.config().property("spring.application.name")
                    .ifPresent(p -> node.addEvidence(TopologyContext.at(p.file(), p.line(), LocationKind.CONFIG)));
            service.ifPresent(s -> node.addEvidence(TopologyContext.at(s.file(), s.line(), LocationKind.CONFIG)));
        }
        for (ComposeService service : unmatched) {
            boolean present = service.directory().filter(d -> !d.isEmpty()).map(d -> hasDirectory(index, d)).orElse(false);
            TNode node = registry.declare(ProjectPaths.nodeId(service.name()), kindOf(service), present);
            node.compose = Optional.of(service);
            node.present = node.present || present;
            service.ports().forEach(p -> node.ports.add(p.containerPort()));
            node.addEvidence(TopologyContext.at(service.file(), service.line(), LocationKind.CONFIG));
        }
        for (TNode node : registry.all()) {
            node.compose.ifPresent(c -> registry.alias(node, c.name()));
        }
        return registry;
    }

    private static boolean describes(ComposeService service, Module module) {
        boolean sameDirectory = service.directory().filter(d -> d.equals(module.dir())).isPresent();
        String name = service.name().toLowerCase(Locale.ROOT);
        return sameDirectory || name.equals(module.name().toLowerCase(Locale.ROOT)) || name.equals(module.directoryName().toLowerCase(Locale.ROOT));
    }

    private static NodeKind kindOf(ComposeService service) {
        String image = service.image().map(i -> i.toLowerCase(Locale.ROOT)).orElse("");
        if (BROKER_IMAGES.stream().anyMatch(image::contains)) {
            return NodeKind.BROKER;
        }
        if (DATABASE_IMAGES.stream().anyMatch(image::contains)) {
            return NodeKind.DATABASE;
        }
        return NodeKind.SERVICE;
    }

    private static boolean hasDirectory(ProjectIndex index, String directory) {
        String prefix = directory + "/";
        return index.files().stream().anyMatch(f -> f.path().value().startsWith(prefix));
    }

    private static Listener listener(ProjectIndex index, Module module, Module.Server server) {
        List<String> certificates = new ArrayList<>();
        server.bundle().flatMap(index.bundles()::get).ifPresent(b -> certificates.addAll(b.keystoreReferences()));
        module.config().value("server.ssl.certificate").ifPresent(certificates::add);
        List<Evidence> evidence = new ArrayList<>();
        server.sslProperty().ifPresent(p -> evidence.add(TopologyContext.at(p.file(), p.line(), LocationKind.CONFIG)));
        Optional<ConfigProperty> auth = module.config().property("server.ssl.client-auth");
        auth.ifPresent(p -> evidence.add(TopologyContext.at(p.file(), p.line(), LocationKind.CONFIG)));
        return new Listener(server.tls(), server.tls() && server.clientAuth().asksForCertificate(), certificates, server.bundle(), evidence);
    }
}
