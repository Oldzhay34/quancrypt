package com.quancrypt.core.domain.event;

import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.Protocol;
import java.util.List;
import java.util.Map;

/** The topology of a scan was recorded for the first time (RecordTopology). */
public record TopologyRecorded(int nodeCount, int linkCount, List<LinkSummary> links) implements DomainEvent {

    /** Coded facts of one link. */
    public record LinkSummary(Protocol protocol, boolean tls, boolean mtls) {
    }

    public TopologyRecorded {
        links = List.copyOf(links);
    }

    @Override
    public EventType type() {
        return EventType.TOPOLOGY_RECORDED;
    }

    @Override
    public Map<String, Object> payload() {
        List<Object> linkPayloads = links.stream()
                .map(l -> (Object) Payloads.of("protocol", l.protocol().name(), "tls", l.tls(), "mtls", l.mtls()))
                .toList();
        return Payloads.of("node_count", nodeCount, "link_count", linkCount, "links", linkPayloads);
    }
}
