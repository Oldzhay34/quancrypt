package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.InitializerDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;

/**
 * A parsed Java file with what detectors need: constant resolution inside the unit (D-190), the JDK/library type a simple
 * name stands for (from the imports, no symbol solving), the symbol of a node (Class#method) and its evidence.
 */
public final class JavaUnit {

    private static final Pattern SYMBOL_PART = Pattern.compile("[^A-Za-z0-9_$.<>#-]");

    private final RelativePath path;
    private final LocationKind location;
    private final CompilationUnit unit;
    private final ConstantResolver constants;

    JavaUnit(RelativePath path, LocationKind location, CompilationUnit unit) {
        this.path = path;
        this.location = location;
        this.unit = unit;
        this.constants = new ConstantResolver(unit);
    }

    public RelativePath path() {
        return path;
    }

    public LocationKind location() {
        return location;
    }

    /** All nodes of a type in the unit (the tree itself is not handed out, it is mutable). */
    public <N extends Node> List<N> findAll(Class<N> type) {
        return unit.findAll(type);
    }

    public Optional<String> string(Expression expression) {
        return constants.string(expression);
    }

    public Optional<Integer> integer(Expression expression) {
        return constants.integer(expression);
    }

    /** The calls of {@code Type.method(..)}, where Type is a simple or qualified type name and may be a library type. */
    public List<MethodCallExpr> calls(String typeSimpleName, String method) {
        List<MethodCallExpr> found = new ArrayList<>();
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            if (call.getNameAsString().equals(method) && call.getScope().filter(s -> simpleName(s).equals(typeSimpleName)).isPresent()) {
                found.add(call);
            }
        }
        return found;
    }

    /**
     * Whether a simple type name stands for the given fully qualified type in this unit: imported by name, imported by its
     * package, or used without any import that would say otherwise.
     */
    public boolean refersTo(String simpleName, String qualifiedName) {
        String packageName = qualifiedName.substring(0, qualifiedName.lastIndexOf('.'));
        boolean otherImport = false;
        for (ImportDeclaration declaration : unit.getImports()) {
            String name = declaration.getNameAsString();
            if (declaration.isAsterisk() && name.equals(packageName)) {
                return true;
            }
            if (!declaration.isAsterisk() && name.equals(qualifiedName)) {
                return true;
            }
            if (!declaration.isAsterisk() && name.endsWith("." + simpleName)) {
                otherImport = true;
            }
        }
        return !otherImport && !declaresType(simpleName);
    }

    public boolean importsPackage(String prefix) {
        return unit.getImports().stream().anyMatch(i -> i.getNameAsString().startsWith(prefix));
    }

    public Evidence evidence(Node node) {
        Optional<LineRange> lines = node.getRange()
                .map(range -> new LineRange(Math.max(1, range.begin.line), Math.max(range.begin.line, range.end.line)));
        return new Evidence(path, lines, location);
    }

    /** Class#method of the declaration around a node; constructors are Class#Class, field initialisers Class#field. */
    public String symbol(Node node) {
        String typeName = fileStem();
        String member = "<class>";
        boolean memberFound = false;
        boolean typeFound = false;
        Optional<Node> current = Optional.of(node);
        while (current.isPresent() && !typeFound) {
            Node ancestor = current.get();
            if (!memberFound && ancestor instanceof CallableDeclaration<?> callable) {
                member = callable.getNameAsString();
                memberFound = true;
            } else if (!memberFound && ancestor instanceof FieldDeclaration field && !field.getVariables().isEmpty()) {
                member = field.getVariable(0).getNameAsString();
                memberFound = true;
            } else if (!memberFound && ancestor instanceof InitializerDeclaration) {
                member = "<clinit>";
                memberFound = true;
            } else if (ancestor instanceof TypeDeclaration<?> type) {
                typeName = type.getNameAsString();
                typeFound = true;
            }
            current = ancestor.getParentNode();
        }
        return clean(typeName + "#" + member);
    }

    private boolean declaresType(String simpleName) {
        return unit.findAll(ClassOrInterfaceDeclaration.class).stream().anyMatch(t -> t.getNameAsString().equals(simpleName))
                || unit.findAll(EnumDeclaration.class).stream().anyMatch(t -> t.getNameAsString().equals(simpleName))
                || unit.findAll(RecordDeclaration.class).stream().anyMatch(t -> t.getNameAsString().equals(simpleName));
    }

    /** The simple type names that declare a field or parameter of the given class, for loader tracing (D-185). */
    public Map<String, Integer> typeNamesUsedAsParametersOrFields() {
        Map<String, Integer> found = new HashMap<>();
        unit.findAll(com.github.javaparser.ast.body.Parameter.class).forEach(p -> found.merge(p.getType().asString(), 1, Integer::sum));
        unit.findAll(VariableDeclarator.class).forEach(v -> found.merge(v.getType().asString(), 1, Integer::sum));
        return found;
    }

    private String fileStem() {
        List<String> segments = path.segments();
        String name = segments.get(segments.size() - 1);
        return name.endsWith(".java") ? name.substring(0, name.length() - 5) : name;
    }

    private static String clean(String symbol) {
        String cleaned = SYMBOL_PART.matcher(symbol).replaceAll("");
        return cleaned.length() > 512 ? cleaned.substring(0, 512) : cleaned;
    }

    /** The last name of a scope expression: {@code Cipher} for both {@code Cipher} and {@code javax.crypto.Cipher}. */
    public static String simpleName(Expression expression) {
        if (expression instanceof NameExpr name) {
            return name.getNameAsString();
        }
        if (expression instanceof FieldAccessExpr access) {
            return access.getNameAsString();
        }
        return "";
    }
}
