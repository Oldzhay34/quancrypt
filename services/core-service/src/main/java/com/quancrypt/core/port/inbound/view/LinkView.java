package com.quancrypt.core.port.inbound.view;

import java.util.List;
import java.util.UUID;

/** A topology link. */
public record LinkView(String source, String target, String protocol, boolean tls, boolean mtls, List<CallSiteView> callSites, List<UUID> findingIds) {

    public LinkView {
        callSites = List.copyOf(callSites);
        findingIds = List.copyOf(findingIds);
    }
}
