package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.NodeKind;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;

/**
 * The nodes of the topology and the names they are known by (compose service name, application name, directory name, host
 * names). A connection's target is resolved here: by name first, then, for a local address, by the one node that listens on the
 * port; what is still unknown becomes an external node named after its host and port.
 */
final class ServiceRegistry {

    private final Map<String, TNode> nodes = new TreeMap<>();
    private final Map<String, TNode> byAlias = new HashMap<>();
    private final Map<String, TNode> byModule = new HashMap<>();

    /** The node with this id, created with the kind and presence when it does not exist yet. */
    TNode declare(String id, NodeKind kind, boolean present) {
        TNode node = nodes.get(id);
        if (node == null) {
            if (nodes.size() >= ServiceGraph.MAX_NODES) {
                throw new SourceTooLargeException("the project has more services than one topology holds");
            }
            node = new TNode(id, kind, present);
            nodes.put(id, node);
            byAlias.putIfAbsent(id.toLowerCase(Locale.ROOT), node);
        }
        return node;
    }

    void alias(TNode node, String name) {
        byAlias.putIfAbsent(name.toLowerCase(Locale.ROOT), node);
    }

    void bind(Module module, TNode node) {
        byModule.put(module.dir(), node);
        node.module = Optional.of(module);
    }

    Optional<TNode> nodeOf(Module module) {
        return Optional.ofNullable(byModule.get(module.dir()));
    }

    Optional<TNode> byName(String name) {
        return Optional.ofNullable(byAlias.get(name.toLowerCase(Locale.ROOT)));
    }

    Optional<TNode> byId(String id) {
        return Optional.ofNullable(nodes.get(id));
    }

    List<TNode> all() {
        return new ArrayList<>(nodes.values());
    }

    /** The node a connection to the target reaches. */
    TNode resolve(Target target, Protocol protocol) {
        if (!target.local()) {
            Optional<TNode> named = byName(target.host()).or(() -> internalName(target.host()).flatMap(this::byName));
            if (named.isPresent()) {
                return named.get();
            }
        } else if (target.port() > 0) {
            List<TNode> listening = nodes.values().stream().filter(n -> n.ports.contains(target.port())).toList();
            if (listening.size() == 1) {
                return listening.get(0);
            }
        }
        String host = target.host().isEmpty() ? "localhost" : target.host();
        String id = ProjectPaths.nodeId(target.port() > 0 ? host + "-" + target.port() : host);
        TNode existing = nodes.get(id);
        return existing != null ? existing : declare(id, kindOf(target, protocol), false);
    }

    /**
     * The service name in a cluster-internal host ({@code billing.shop.svc}, {@code billing.shop.svc.cluster.local}, {@code db.local}):
     * its first label. An outside host such as {@code auth.partner.com} is never shortened, so it cannot be taken for a service of
     * the project that happens to be called {@code auth}.
     */
    private static Optional<String> internalName(String host) {
        boolean internal = host.endsWith(".svc") || host.contains(".svc.") || host.endsWith(".local");
        int dot = host.indexOf('.');
        return internal && dot > 0 ? Optional.of(host.substring(0, dot)) : Optional.empty();
    }

    private static NodeKind kindOf(Target target, Protocol protocol) {
        if (target.scheme().equals("jdbc")) {
            return NodeKind.DATABASE;
        }
        return switch (protocol) {
            case MQTT, AMQP, KAFKA -> NodeKind.BROKER;
            default -> NodeKind.EXTERNAL;
        };
    }
}
