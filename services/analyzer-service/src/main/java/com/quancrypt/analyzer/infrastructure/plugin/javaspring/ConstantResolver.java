package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.BinaryExpr;
import com.github.javaparser.ast.expr.EnclosedExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.IntegerLiteralExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import com.github.javaparser.ast.expr.ThisExpr;
import com.github.javaparser.ast.expr.TextBlockLiteralExpr;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * Resolves string and int constants inside one compilation unit: literals, concatenations and {@code static final}
 * fields of the unit. Nothing across files or projects is resolved (P3.2): anything else is unresolved and the detector
 * reports UNKNOWN at a low confidence. A resolved string is at most {@value #MAX_LENGTH} characters: algorithm names, file
 * names and the like are short, and a longer value (a generated constant) must not be built again for every use.
 */
final class ConstantResolver {

    private static final int MAX_DEPTH = 8;
    static final int MAX_LENGTH = 1024;

    private final Map<String, Expression> fields = new HashMap<>();
    private final Set<String> types = new HashSet<>();

    ConstantResolver(CompilationUnit unit) {
        unit.findAll(ClassOrInterfaceDeclaration.class).forEach(type -> types.add(type.getNameAsString()));
        unit.findAll(EnumDeclaration.class).forEach(type -> types.add(type.getNameAsString()));
        unit.findAll(RecordDeclaration.class).forEach(type -> types.add(type.getNameAsString()));
        for (FieldDeclaration field : unit.findAll(FieldDeclaration.class)) {
            boolean constant = field.isFinal() && (field.isStatic() || field.getParentNode()
                    .filter(parent -> parent instanceof com.github.javaparser.ast.body.ClassOrInterfaceDeclaration declaration
                            && declaration.isInterface()).isPresent());
            if (!constant) {
                continue;
            }
            for (VariableDeclarator variable : field.getVariables()) {
                variable.getInitializer().ifPresent(initializer -> fields.putIfAbsent(variable.getNameAsString(), initializer));
            }
        }
    }

    Optional<String> string(Expression expression) {
        return string(expression, new HashSet<>(), 0);
    }

    Optional<Integer> integer(Expression expression) {
        return integer(expression, new HashSet<>(), 0);
    }

    private Optional<String> string(Expression expression, Set<String> visiting, int depth) {
        if (depth > MAX_DEPTH) {
            return Optional.empty();
        }
        if (expression instanceof StringLiteralExpr literal) {
            return literal.getValue().length() > MAX_LENGTH ? Optional.empty() : Optional.of(literal.asString());
        }
        if (expression instanceof TextBlockLiteralExpr block) {
            return block.getValue().length() > MAX_LENGTH ? Optional.empty() : Optional.of(block.asString());
        }
        if (expression instanceof EnclosedExpr enclosed) {
            return string(enclosed.getInner(), visiting, depth + 1);
        }
        if (expression instanceof BinaryExpr binary && binary.getOperator() == BinaryExpr.Operator.PLUS) {
            Optional<String> left = string(binary.getLeft(), visiting, depth + 1);
            Optional<String> right = left.isPresent() ? string(binary.getRight(), visiting, depth + 1) : Optional.empty();
            if (left.isPresent() && right.isPresent() && left.get().length() + right.get().length() <= MAX_LENGTH) {
                return Optional.of(left.get() + right.get());
            }
            return Optional.empty();
        }
        String name = constantName(expression);
        if (name != null && fields.containsKey(name) && visiting.add(name)) {
            try {
                return string(fields.get(name), visiting, depth + 1);
            } finally {
                visiting.remove(name);
            }
        }
        return Optional.empty();
    }

    private Optional<Integer> integer(Expression expression, Set<String> visiting, int depth) {
        if (depth > MAX_DEPTH) {
            return Optional.empty();
        }
        if (expression instanceof IntegerLiteralExpr literal) {
            try {
                return Optional.of(literal.asNumber().intValue());
            } catch (IllegalStateException | NumberFormatException e) {
                return Optional.empty();
            }
        }
        if (expression instanceof EnclosedExpr enclosed) {
            return integer(enclosed.getInner(), visiting, depth + 1);
        }
        String name = constantName(expression);
        if (name != null && fields.containsKey(name) && visiting.add(name)) {
            try {
                return integer(fields.get(name), visiting, depth + 1);
            } finally {
                visiting.remove(name);
            }
        }
        return Optional.empty();
    }

    /** The simple name of a constant of this unit: {@code NAME}, {@code this.NAME} or {@code OwnType.NAME}; a field of another type is not ours. */
    private String constantName(Expression expression) {
        if (expression instanceof NameExpr name) {
            return name.getNameAsString();
        }
        if (expression instanceof FieldAccessExpr access) {
            boolean own = access.getScope() instanceof ThisExpr
                    || access.getScope() instanceof NameExpr scope && types.contains(scope.getNameAsString());
            return own ? access.getNameAsString() : null;
        }
        return null;
    }
}
