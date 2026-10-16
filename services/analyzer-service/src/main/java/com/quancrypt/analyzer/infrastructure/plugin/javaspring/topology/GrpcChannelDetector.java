package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.github.javaparser.ast.expr.MethodCallExpr;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * gRPC channels built in code: {@code ManagedChannelBuilder.forAddress(host, port)} and {@code forTarget("host:port")} (also on
 * the Netty and OkHttp builders). Only what the chain says is reported as encrypted: {@code useTransportSecurity()} or a
 * {@code sslContext(..)} is TLS, {@code usePlaintext()} is not; a channel without either is reported without TLS because the
 * code does not show any.
 */
final class GrpcChannelDetector implements UnitTopologyDetector {

    static final String ID = "topology.grpc-channel";
    private static final Set<String> BUILDERS = Set.of("ManagedChannelBuilder", "NettyChannelBuilder", "OkHttpChannelBuilder");
    private static final Set<String> SECURE_CALLS = Set.of("useTransportSecurity", "sslContext");

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, JavaUnit unit, TopologySink sink) {
        TNode node = context.nodeOf(unit.path()).orElse(null);
        if (node == null) {
            return;
        }
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            boolean builder = call.getScope().filter(s -> BUILDERS.contains(JavaUnit.simpleName(s))).isPresent();
            if (!builder || !(call.getNameAsString().equals("forAddress") || call.getNameAsString().equals("forTarget"))) {
                continue;
            }
            Optional<Target> target = call.getNameAsString().equals("forAddress") ? address(unit, call) : targetOf(unit, call);
            target.ifPresent(t -> sink.edge(new RawEdge(node.id, t, Protocol.GRPC, secure(call), List.of(unit.evidence(call)), Set.of(), Set.of())));
        }
    }

    private static Optional<Target> address(JavaUnit unit, MethodCallExpr call) {
        if (call.getArguments().size() != 2) {
            return Optional.empty();
        }
        Optional<String> host = unit.string(call.getArgument(0));
        Optional<Integer> port = unit.integer(call.getArgument(1));
        if (host.isEmpty() || port.isEmpty() || port.get() < 1 || port.get() > 65535) {
            return Optional.empty();
        }
        return Target.ofName(host.get()).map(t -> new Target(t.host(), port.get(), ""));
    }

    private static Optional<Target> targetOf(JavaUnit unit, MethodCallExpr call) {
        if (call.getArguments().size() != 1) {
            return Optional.empty();
        }
        return unit.string(call.getArgument(0)).map(text -> text.startsWith("dns:///") ? text.substring("dns:///".length()) : text)
                .flatMap(text -> Target.ofHostPort(text).or(() -> Target.ofName(text)));
    }

    /** Whether the builder chain that starts at the call says the channel is encrypted. */
    private static boolean secure(MethodCallExpr start) {
        MethodCallExpr current = start;
        while (true) {
            Optional<MethodCallExpr> next = parentCall(current);
            if (next.isEmpty()) {
                return false;
            }
            if (SECURE_CALLS.contains(next.get().getNameAsString())) {
                return true;
            }
            current = next.get();
        }
    }

    private static Optional<MethodCallExpr> parentCall(MethodCallExpr child) {
        return child.getParentNode().filter(MethodCallExpr.class::isInstance).map(MethodCallExpr.class::cast)
                .filter(parent -> parent.getScope().filter(scope -> scope == child).isPresent());
    }
}
