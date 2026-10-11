package com.quancrypt.core.facade.dto;

import java.util.List;
import java.util.UUID;

/** Topology link (schema LinkInput). */
public record LinkDto(String source, String target, String protocol, boolean tls, boolean mtls, List<CallSiteDto> callSites, List<UUID> findingIds) {

    public LinkDto {
        callSites = callSites == null ? null : List.copyOf(callSites);
        findingIds = findingIds == null ? null : List.copyOf(findingIds);
    }
}

