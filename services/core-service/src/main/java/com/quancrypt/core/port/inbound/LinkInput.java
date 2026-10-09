package com.quancrypt.core.port.inbound;

import java.util.List;
import java.util.UUID;

/** One topology link between two node names. */
public record LinkInput(String source, String target, String protocol, boolean tls, boolean mtls, List<CallSiteInput> callSites, List<UUID> findingIds) {

    public LinkInput {
        callSites = List.copyOf(callSites);
        findingIds = List.copyOf(findingIds);
    }
}
