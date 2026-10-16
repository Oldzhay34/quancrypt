package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.github.javaparser.ast.expr.MethodCallExpr;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * Facts about a module that only its Java code tells: the SSL bundles it asks for and the TLS groups it names with
 * {@code System.setProperty("jdk.tls.namedGroups", ...)}. They are collected while each Java file is parsed (the tree is dropped
 * afterwards) and read when the edges are mapped.
 */
final class ModuleFacts {

    static final String GROUPS_PROPERTY = "jdk.tls.namedGroups";

    private final Map<String, Set<String>> bundles = new HashMap<>();
    private final Map<String, String> groups = new HashMap<>();

    void collect(Module module, JavaUnit unit) {
        bundles.computeIfAbsent(module.dir(), d -> new LinkedHashSet<>()).addAll(JavaClients.bundles(unit));
        if (groups.containsKey(module.dir())) {
            return;
        }
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            if (call.getNameAsString().equals("setProperty") && call.getArguments().size() == 2
                    && unit.string(call.getArgument(0)).filter(GROUPS_PROPERTY::equals).isPresent()) {
                Optional<String> value = unit.string(call.getArgument(1));
                if (value.isPresent()) {
                    groups.putIfAbsent(module.dir(), value.get());
                    return;
                }
            }
        }
    }

    /** The bundle names the module's Java files ask for. */
    Set<String> bundles(Module module) {
        return bundles.getOrDefault(module.dir(), Set.of());
    }

    /** The first constant group list the module's code sets. */
    Optional<String> groups(Module module) {
        return Optional.ofNullable(groups.get(module.dir()));
    }
}
