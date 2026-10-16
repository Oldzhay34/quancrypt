package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * HTTP clients in Java code: {@code RestTemplate}, {@code RestClient} and {@code WebClient}. A file that builds one connects
 * to the URLs of the module configuration it reads (an accessor named like the key, {@code accountServiceUrl()} for
 * {@code qbank.account-service-url}) and to the URL literals it contains. The SSL bundles the file asks for are the client
 * identity of those connections.
 */
final class HttpClientCallDetector implements UnitTopologyDetector {

    static final String ID = "topology.http-client";
    private static final List<String> CLIENT_PACKAGES = List.of("org.springframework.web.client",
            "org.springframework.web.reactive.function.client", "org.springframework.http.client");
    private static final Set<String> BUILDERS = Set.of("RestClient", "WebClient");

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, JavaUnit unit, TopologySink sink) {
        if (CLIENT_PACKAGES.stream().noneMatch(unit::importsPackage)) {
            return;
        }
        Module module = context.modules().of(unit.path()).orElse(null);
        TNode node = context.nodeOf(unit.path()).orElse(null);
        if (module == null || node == null) {
            return;
        }
        List<Node> creations = clientCreations(unit);
        Set<String> bundles = JavaClients.bundles(unit);
        Map<String, List<Node>> identifiers = JavaClients.identifiers(unit);
        for (ConfigUrls.UrlProperty url : ConfigUrls.of(module)) {
            if (url.protocol() != Protocol.HTTP) {
                continue;
            }
            List<Node> mentions = JavaClients.mentions(identifiers, url.property().key());
            if (mentions.isEmpty()) {
                continue;
            }
            List<Node> seen = new ArrayList<>(creations);
            seen.addAll(mentions);
            sink.edge(new RawEdge(node.id, url.target(), Protocol.HTTP, url.target().secureScheme(), JavaClients.evidence(unit, seen), bundles, Set.of()));
        }
        for (StringLiteralExpr literal : unit.findAll(StringLiteralExpr.class)) {
            Target.ofUrl(literal.asString()).filter(t -> t.protocol().filter(p -> p == Protocol.HTTP).isPresent()).ifPresent(
                    target -> sink.edge(new RawEdge(node.id, target, Protocol.HTTP, target.secureScheme(), List.of(unit.evidence(literal)), bundles,
                            Set.of())));
        }
    }

    private static List<Node> clientCreations(JavaUnit unit) {
        List<Node> found = new ArrayList<>();
        for (ObjectCreationExpr creation : unit.findAll(ObjectCreationExpr.class)) {
            if (creation.getType().getNameAsString().equals("RestTemplate")) {
                found.add(creation);
            }
        }
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            boolean factory = call.getNameAsString().equals("builder") || call.getNameAsString().equals("create");
            if (factory && call.getScope().filter(s -> BUILDERS.contains(JavaUnit.simpleName(s))).isPresent()) {
                found.add(call);
            }
        }
        return found;
    }
}
