package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.LocationKind;

/**
 * The routes of a Spring Cloud Gateway ({@code spring.cloud.gateway.*.routes[n].uri}): each route is a connection from the
 * gateway to the service behind it. A {@code lb://name} URI names the target service; the SSL bundle of the gateway's HTTP
 * client is the one configured next to the routes.
 */
final class GatewayRouteDetector implements TopologyDetector {

    static final String ID = "topology.gateway-route";

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, TopologySink sink) {
        for (Module module : context.modules().all()) {
            context.registry().nodeOf(module).ifPresent(node -> {
                for (ConfigUrls.UrlProperty route : ConfigUrls.routes(module)) {
                    context.index().tree().checkpoint();
                    RawEdge edge = RawEdge.of(node.id, route.target(), route.protocol(), route.target().secureScheme(),
                            TopologyContext.at(route.property().file(), route.property().line(), LocationKind.CONFIG));
                    sink.edge(edge.withBundles(ConfigUrls.bundlesNear(module, route.property().key())));
                }
            });
        }
    }
}
