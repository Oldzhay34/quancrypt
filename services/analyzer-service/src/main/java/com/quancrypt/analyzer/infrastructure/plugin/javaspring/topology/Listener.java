package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.Evidence;
import java.util.List;
import java.util.Optional;

/**
 * What a node's server side says about TLS: whether it listens with a certificate, whether it asks clients for one, the
 * certificate file references and bundle names it presents (for the findings of an edge), and where it said so.
 */
record Listener(boolean tls, boolean asksForClientCertificate, List<String> certificateFiles, Optional<String> serverBundle,
        List<Evidence> evidence) {

    static final Listener NONE = new Listener(false, false, List.of(), Optional.empty(), List.of());

    Listener {
        certificateFiles = List.copyOf(certificateFiles);
        evidence = List.copyOf(evidence);
    }
}
