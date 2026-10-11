package com.quancrypt.analyzer.port.inbound;

import java.util.List;

/** A topology edge. */
public record EdgeView(String source, String target, String protocol, boolean tls, boolean mtls, List<EvidenceView> evidence) {

    public EdgeView {
        evidence = List.copyOf(evidence);
    }
}
