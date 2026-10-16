package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.LocationKind;

/**
 * The service URLs of a module's Spring configuration: a property whose value is a connection URL (http, https, ssl, tcp,
 * mqtt, amqp, grpc, jdbc ...) is a connection from the module to that address, seen at the property's line. Which SSL bundle the
 * client presents is decided by the code that uses the URL (HttpClientCallDetector, MqttTopologyDetector) or by a bundle
 * reference configured next to the key.
 */
final class SpringClientConfigDetector implements TopologyDetector {

    static final String ID = "topology.spring-client-config";

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, TopologySink sink) {
        for (Module module : context.modules().all()) {
            context.registry().nodeOf(module).ifPresent(node -> {
                for (ConfigUrls.UrlProperty url : ConfigUrls.of(module)) {
                    RawEdge edge = RawEdge.of(node.id, url.target(), url.protocol(), url.target().secureScheme(),
                            TopologyContext.at(url.property().file(), url.property().line(), LocationKind.CONFIG));
                    sink.edge(edge.withBundles(ConfigUrls.bundlesNear(module, url.property().key())));
                }
            });
        }
    }
}
