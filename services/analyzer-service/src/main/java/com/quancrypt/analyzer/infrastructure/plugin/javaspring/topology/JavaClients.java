package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** What the Java topology detectors ask of a parsed file: the SSL bundles it uses and where it reads a configuration key. */
final class JavaClients {

    static final int MAX_EVIDENCE = 20;

    private JavaClients() {
    }

    /** The names of SSL bundles the file asks for with {@code getBundle("name")}. */
    static Set<String> bundles(JavaUnit unit) {
        Set<String> names = new LinkedHashSet<>();
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            if (call.getNameAsString().equals("getBundle") && call.getArguments().size() == 1) {
                unit.string(call.getArgument(0)).ifPresent(names::add);
            }
        }
        return names;
    }

    /**
     * The nodes of the file by the spelling a configuration key can be read with: a method call, a name or a field access
     * ({@code accountServiceUrl()}, {@code getAccountServiceUrl()}) under its relaxed name. Built once per file, so asking for a
     * key costs a lookup and not a walk over the tree.
     */
    static Map<String, List<Node>> identifiers(JavaUnit unit) {
        Map<String, List<Node>> found = new HashMap<>();
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            add(found, call.getNameAsString(), call);
        }
        for (NameExpr name : unit.findAll(NameExpr.class)) {
            add(found, name.getNameAsString(), name);
        }
        for (FieldAccessExpr access : unit.findAll(FieldAccessExpr.class)) {
            add(found, access.getNameAsString(), access);
        }
        return found;
    }

    /** The nodes that read the configuration key, from an index made by {@link #identifiers(JavaUnit)}. */
    static List<Node> mentions(Map<String, List<Node>> identifiers, String configKey) {
        return identifiers.getOrDefault(ConfigUrls.relaxed(ConfigUrls.lastSegment(configKey)), List.of());
    }

    private static void add(Map<String, List<Node>> found, String identifier, Node node) {
        found.computeIfAbsent(ConfigUrls.relaxed(identifier), k -> new ArrayList<>()).add(node);
        if (identifier.length() > 3 && identifier.startsWith("get") && Character.isUpperCase(identifier.charAt(3))) {
            found.computeIfAbsent(ConfigUrls.relaxed(identifier.substring(3)), k -> new ArrayList<>()).add(node);
        }
    }

    /** The first nodes as evidence, at most {@link #MAX_EVIDENCE}. */
    static List<Evidence> evidence(JavaUnit unit, List<? extends Node> nodes) {
        List<Evidence> evidence = new ArrayList<>();
        for (Node node : nodes) {
            if (evidence.size() >= MAX_EVIDENCE) {
                break;
            }
            Evidence one = unit.evidence(node);
            if (evidence.size() < MAX_EVIDENCE && !evidence.contains(one)) {
                evidence.add(one);
            }
        }
        return evidence;
    }

    /** A configuration value with placeholders resolved, or empty when a placeholder stays open. */
    static Optional<String> resolved(Module module, String text) {
        String value = module.config().resolved(text).strip();
        return value.isEmpty() || value.contains("${") ? Optional.empty() : Optional.of(value);
    }
}
