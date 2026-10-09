package com.quancrypt.core.domain.model;

import java.util.List;
import java.util.Set;
import java.util.UUID;

/** A call between two nodes: the source is the client, the target the server. */
public record ServiceLink(
        UUID id,
        UUID sourceNodeId,
        UUID targetNodeId,
        Protocol protocol,
        boolean tls,
        boolean mtls,
        List<CallSite> callSites,
        Set<UUID> findingIds) {

    public ServiceLink {
        if (sourceNodeId.equals(targetNodeId)) {
            throw new IllegalArgumentException("a link needs two different nodes");
        }
        if (mtls && !tls) {
            throw new IllegalArgumentException("mutual TLS requires TLS");
        }
        callSites = List.copyOf(callSites);
        findingIds = Set.copyOf(findingIds);
    }
}
