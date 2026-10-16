package com.quancrypt.analyzer.domain.model;

import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * A connection from the node that opens it (client) to the node that listens (server). mTLS implies TLS. {@code findings}
 * are the crypto findings the connection uses and {@code keyExchange} the inferred key exchange of its TLS (D-208).
 */
public record ServiceEdge(String source, String target, Protocol protocol, boolean tls, boolean mtls, List<Evidence> evidence,
        List<FindingRef> findings, Optional<KeyExchange> keyExchange) {

    public static final int MAX_FINDINGS = 500;

    public ServiceEdge {
        Text.matching(source, Text.NODE_ID, "source");
        Text.matching(target, Text.NODE_ID, "target");
        Objects.requireNonNull(protocol, "protocol");
        if (mtls && !tls) {
            throw new IllegalArgumentException("an mTLS edge is also a TLS edge");
        }
        evidence = List.copyOf(evidence);
        if (evidence.size() > ServiceNode.MAX_EVIDENCE) {
            throw new IllegalArgumentException("an edge has at most 100 evidence entries");
        }
        findings = List.copyOf(findings);
        if (findings.size() > MAX_FINDINGS) {
            throw new IllegalArgumentException("an edge has at most 500 findings");
        }
        Objects.requireNonNull(keyExchange, "keyExchange");
        if (keyExchange.isPresent() && !tls) {
            throw new IllegalArgumentException("only a TLS edge has a key exchange");
        }
    }

    /** An edge without crypto details. */
    public ServiceEdge(String source, String target, Protocol protocol, boolean tls, boolean mtls, List<Evidence> evidence) {
        this(source, target, protocol, tls, mtls, evidence, List.of(), Optional.empty());
    }
}
