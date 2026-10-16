package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;

/**
 * Message broker connections in Spring configuration: Kafka ({@code spring.kafka.bootstrap-servers}) and RabbitMQ
 * ({@code spring.rabbitmq.addresses}, or {@code host} and {@code port}). TLS is seen from the SSL settings of the client; the
 * client identity is its SSL bundle or the key store it names. A broker that is not part of the project becomes a broker node
 * named after its address.
 */
final class MessagingConfigDetector implements TopologyDetector {

    static final String ID = "topology.messaging-config";

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, TopologySink sink) {
        for (Module module : context.modules().all()) {
            context.registry().nodeOf(module).ifPresent(node -> {
                kafka(module, node, sink);
                rabbit(module, node, sink);
            });
        }
    }

    private static void kafka(Module module, TNode node, TopologySink sink) {
        List<ConfigProperty> servers = module.config().all().stream()
                .filter(p -> p.key().equals("spring.kafka.bootstrap-servers") || p.key().startsWith("spring.kafka.bootstrap-servers[")).toList();
        boolean tls = module.config().hasKeyStartingWith("spring.kafka.ssl.") || securityProtocolIsSsl(module, "spring.kafka.security.protocol")
                || securityProtocolIsSsl(module, "spring.kafka.properties.security.protocol");
        Set<String> bundles = module.config().value("spring.kafka.ssl.bundle").map(Set::of).orElse(Set.of());
        Set<String> identity = keyStore(module, "spring.kafka.ssl.key-store-location");
        for (ConfigProperty server : servers) {
            for (String address : module.config().resolved(server.value()).split(",")) {
                address(address).ifPresent(target -> sink.edge(new RawEdge(node.id, target, Protocol.KAFKA, tls || target.secureScheme(),
                        List.of(TopologyContext.at(server.file(), server.line(), LocationKind.CONFIG)), bundles, identity)));
            }
        }
    }

    private static void rabbit(Module module, TNode node, TopologySink sink) {
        boolean tls = module.config().value("spring.rabbitmq.ssl.enabled").filter(v -> v.equalsIgnoreCase("true")).isPresent();
        Set<String> bundles = module.config().value("spring.rabbitmq.ssl.bundle").map(Set::of).orElse(Set.of());
        Set<String> identity = keyStore(module, "spring.rabbitmq.ssl.key-store");
        Optional<ConfigProperty> addresses = module.config().property("spring.rabbitmq.addresses");
        List<Target> targets = new ArrayList<>();
        ConfigProperty seen;
        if (addresses.isPresent()) {
            seen = addresses.get();
            for (String address : module.config().resolved(seen.value()).split(",")) {
                address(address).ifPresent(targets::add);
            }
        } else if (module.config().property("spring.rabbitmq.host").isPresent()) {
            seen = module.config().property("spring.rabbitmq.host").get();
            String host = module.config().resolved(seen.value()).strip();
            int port = module.config().value("spring.rabbitmq.port").map(MessagingConfigDetector::port).orElse(-1);
            Target.ofName(host).ifPresent(t -> targets.add(new Target(t.host(), port, "")));
        } else {
            return;
        }
        for (Target target : targets) {
            sink.edge(new RawEdge(node.id, target, Protocol.AMQP, tls || target.secureScheme(), List.of(TopologyContext.at(seen.file(), seen.line(), LocationKind.CONFIG)),
                    bundles, identity));
        }
    }

    private static Optional<Target> address(String text) {
        String address = text.strip();
        return Target.ofHostPort(address).or(() -> Target.ofUrl(address)).or(() -> Target.ofName(address));
    }

    private static boolean securityProtocolIsSsl(Module module, String key) {
        return module.config().value(key).map(v -> v.toUpperCase(Locale.ROOT).contains("SSL")).orElse(false);
    }

    private static Set<String> keyStore(Module module, String key) {
        Set<String> refs = new LinkedHashSet<>();
        module.config().value(key).filter(v -> !v.isEmpty()).ifPresent(refs::add);
        return refs;
    }

    private static int port(String text) {
        try {
            int port = Integer.parseInt(text.strip());
            return port > 0 && port <= 65535 ? port : -1;
        } catch (NumberFormatException e) {
            return -1;
        }
    }
}
