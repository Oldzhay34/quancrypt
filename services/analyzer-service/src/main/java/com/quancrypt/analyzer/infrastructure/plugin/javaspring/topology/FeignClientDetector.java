package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MemberValuePair;
import com.github.javaparser.ast.expr.NormalAnnotationExpr;
import com.github.javaparser.ast.expr.SingleMemberAnnotationExpr;
import com.quancrypt.analyzer.domain.model.Protocol;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * Feign clients: {@code @FeignClient(name = "x")}, {@code @FeignClient("x")} and {@code url = "..."}. The URL wins when there
 * is one; otherwise the name is the service the calls go to. Placeholders are resolved against the module configuration.
 */
final class FeignClientDetector implements UnitTopologyDetector {

    static final String ID = "topology.feign-client";

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public void detect(TopologyContext context, JavaUnit unit, TopologySink sink) {
        Module module = context.modules().of(unit.path()).orElse(null);
        TNode node = context.nodeOf(unit.path()).orElse(null);
        if (module == null || node == null) {
            return;
        }
        for (AnnotationExpr annotation : unit.findAll(AnnotationExpr.class)) {
            if (!annotation.getNameAsString().equals("FeignClient") && !annotation.getNameAsString().endsWith(".FeignClient")) {
                continue;
            }
            Optional<String> url = member(unit, module, annotation, "url").filter(v -> !v.isEmpty());
            Optional<String> name = member(unit, module, annotation, "name").or(() -> member(unit, module, annotation, "value"));
            Optional<Target> target = url.flatMap(Target::ofUrl).or(() -> name.flatMap(FeignClientDetector::byName));
            target.ifPresent(t -> sink.edge(new RawEdge(node.id, t, Protocol.HTTP, t.secureScheme(), List.of(unit.evidence(annotation)), Set.of(),
                    Set.of())));
        }
    }

    private static Optional<Target> byName(String name) {
        return Target.ofUrl(name).or(() -> Target.ofName(name));
    }

    private static Optional<String> member(JavaUnit unit, Module module, AnnotationExpr annotation, String member) {
        Optional<Expression> expression = Optional.empty();
        if (annotation instanceof NormalAnnotationExpr normal) {
            expression = normal.getPairs().stream().filter(p -> p.getNameAsString().equals(member)).map(MemberValuePair::getValue).findFirst();
        } else if (annotation instanceof SingleMemberAnnotationExpr single && member.equals("value")) {
            expression = Optional.of(single.getMemberValue());
        }
        return expression.flatMap(unit::string).flatMap(text -> JavaClients.resolved(module, text));
    }
}
