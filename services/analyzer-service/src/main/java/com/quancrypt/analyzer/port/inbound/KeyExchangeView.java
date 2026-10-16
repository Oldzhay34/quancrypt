package com.quancrypt.analyzer.port.inbound;

import java.util.List;

/** The inferred key exchange of a TLS edge (D-208). */
public record KeyExchangeView(String groupFamily, List<String> groups, boolean inferred, double confidence) {

    public KeyExchangeView {
        groups = List.copyOf(groups);
    }
}
