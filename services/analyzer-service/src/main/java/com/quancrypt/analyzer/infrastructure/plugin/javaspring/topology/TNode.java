package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.NodeKind;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** A node while the topology is being built: what is known about it grows as detectors run. */
final class TNode {

    final String id;
    NodeKind kind;
    /** Whether the project itself contains the node (a module, a service with a build directory, a broker configuration). */
    boolean present;
    final Set<Integer> ports = new TreeSet<>();
    final List<Evidence> evidence = new ArrayList<>();
    Optional<Module> module = Optional.empty();
    Optional<ComposeService> compose = Optional.empty();
    /** The listener of a module (its server settings); a broker keeps one per listening port in {@link #listeners}. */
    Listener listener = Listener.NONE;
    /** The listeners of a broker by port; the key 0 is the default listener, whose settings come before the first {@code listener} line. */
    final Map<Integer, Listener> listeners = new TreeMap<>();

    TNode(String id, NodeKind kind, boolean present) {
        this.id = id;
        this.kind = kind;
        this.present = present;
    }

    void addEvidence(Evidence added) {
        if (evidence.size() < com.quancrypt.analyzer.domain.model.ServiceNode.MAX_EVIDENCE && !evidence.contains(added)) {
            evidence.add(added);
        }
    }

    /**
     * What the server side of a connection to this node on the port says about TLS: the listener of that port; with no port written,
     * the only listener, or with several the TLS facts every one of them has (nothing is claimed that one of them lacks).
     */
    Listener listenerFor(int port) {
        if (listeners.isEmpty()) {
            return listener;
        }
        if (port > 0) {
            // a port no listener of the configuration has claims nothing: no TLS is assumed for it
            return listeners.getOrDefault(port, Listener.NONE);
        }
        if (listeners.size() == 1) {
            return listeners.values().iterator().next();
        }
        boolean allTls = listeners.values().stream().allMatch(Listener::tls);
        boolean allAsk = allTls && listeners.values().stream().allMatch(Listener::asksForClientCertificate);
        List<Evidence> evidence = new ArrayList<>();
        listeners.values().forEach(l -> evidence.addAll(l.evidence()));
        List<String> certificates = new ArrayList<>();
        listeners.values().forEach(l -> certificates.addAll(l.certificateFiles()));
        return new Listener(allTls, allAsk, certificates, Optional.empty(), evidence);
    }
}
