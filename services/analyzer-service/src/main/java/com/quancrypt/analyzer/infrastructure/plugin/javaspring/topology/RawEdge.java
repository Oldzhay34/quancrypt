package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.Protocol;
import java.util.List;
import java.util.Set;

/**
 * A connection a detector saw before its ends are resolved to nodes: the caller's node id, where it goes, and what the
 * detector knows about the client's TLS identity. Edges with the same ends and protocol are merged by the assembler.
 *
 * @param sourceId           id of the calling node, as the registry knows it
 * @param target             where the connection goes
 * @param protocol           the protocol
 * @param tls                whether the evidence says the connection is encrypted (a secure URL scheme, an explicit setting)
 * @param evidence           where the connection was seen
 * @param clientBundles      SSL bundle names the client uses (their keystore is the client identity)
 * @param clientCertificates certificate file references the client presents (a mounted certificate and key pair)
 */
record RawEdge(String sourceId, Target target, Protocol protocol, boolean tls, List<Evidence> evidence, Set<String> clientBundles,
        Set<String> clientCertificates) {

    RawEdge {
        evidence = List.copyOf(evidence);
        clientBundles = Set.copyOf(clientBundles);
        clientCertificates = Set.copyOf(clientCertificates);
    }

    static RawEdge of(String sourceId, Target target, Protocol protocol, boolean tls, Evidence evidence) {
        return new RawEdge(sourceId, target, protocol, tls, List.of(evidence), Set.of(), Set.of());
    }

    RawEdge withBundles(Set<String> bundles) {
        return new RawEdge(sourceId, target, protocol, tls, evidence, bundles, clientCertificates);
    }
}
