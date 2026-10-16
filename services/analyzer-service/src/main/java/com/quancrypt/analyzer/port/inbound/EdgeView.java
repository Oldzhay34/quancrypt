package com.quancrypt.analyzer.port.inbound;

import java.util.List;
import java.util.Optional;

/** A topology edge. */
public record EdgeView(String source, String target, String protocol, boolean tls, boolean mtls, List<EvidenceView> evidence,
        List<FindingRefView> findings, Optional<KeyExchangeView> keyExchange) {

    public EdgeView {
        evidence = List.copyOf(evidence);
        findings = List.copyOf(findings);
    }

    /** An edge without crypto details. */
    public EdgeView(String source, String target, String protocol, boolean tls, boolean mtls, List<EvidenceView> evidence) {
        this(source, target, protocol, tls, mtls, evidence, List.of(), Optional.empty());
    }
}
