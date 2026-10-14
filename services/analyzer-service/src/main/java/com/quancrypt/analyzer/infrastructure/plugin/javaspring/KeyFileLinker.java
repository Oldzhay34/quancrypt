package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.BodyDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.BinaryExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import com.github.javaparser.ast.stmt.Statement;
import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemFacts;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemRole;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

/**
 * Finds out what a key file is used for by following the code that loads it (D-185). A Java file that passes the file
 * name (a literal, a constant or a concatenation of both) to a call or constructor of a project class links the file to
 * that class; the usage comes from the crypto findings of the classes that declare or take that class (a key holder is
 * usually handed to the signer, the tokenizer or the TLS setup). A usage the findings agree on is taken; otherwise the
 * most frequent one when it is unique; otherwise UNKNOWN. The same links give findings a key size they cannot know
 * from code (the size read from a key file reaches the class that uses it). No name list is involved, only project code.
 * The class is one algorithm in two halves, collecting references per unit and resolving them once all units are seen; the
 * halves share the reference and unit lists, so splitting them would only pass the same two lists around.
 */
final class KeyFileLinker {

    /** What the linking decided. */
    record Linking(Map<RelativePath, UsageContext> usages, Map<RelativePath, Map<AlgorithmFamily, Set<Integer>>> keySizes) {

        static final Linking NONE = new Linking(Map.of(), Map.of());

        Optional<UsageContext> usageOf(RelativePath keyFile) {
            return Optional.ofNullable(usages.get(keyFile));
        }

        Optional<Integer> keySizeFor(RelativePath javaFile, AlgorithmFamily family) {
            Set<Integer> sizes = keySizes.getOrDefault(javaFile, Map.of()).getOrDefault(family, Set.of());
            return sizes.size() == 1 ? Optional.of(sizes.iterator().next()) : Optional.empty();
        }
    }

    private record Reference(RelativePath from, boolean fromTestCode, String fileName, Set<String> calledTypes) {
    }

    private record UnitFacts(RelativePath file, Set<String> declaredTypes, Set<String> usedTypes) {
    }

    private final Set<String> keyFileNames;
    private final PemIndex pem;
    private final List<Reference> references = new ArrayList<>();
    private final List<UnitFacts> units = new ArrayList<>();

    KeyFileLinker(PemIndex pem) {
        this.pem = pem;
        Set<String> names = new HashSet<>();
        pem.all().forEach(f -> names.add(PemIndex.baseName(f.file())));
        this.keyFileNames = names;
    }

    void collect(JavaUnit unit) {
        Set<String> declared = new TreeSet<>();
        unit.findAll(ClassOrInterfaceDeclaration.class).forEach(t -> declared.add(t.getNameAsString()));
        unit.findAll(EnumDeclaration.class).forEach(t -> declared.add(t.getNameAsString()));
        unit.findAll(RecordDeclaration.class).forEach(t -> declared.add(t.getNameAsString()));
        Set<String> used = new TreeSet<>();
        unit.typeNamesUsedAsParametersOrFields().keySet().forEach(type -> used.add(simpleType(type)));
        units.add(new UnitFacts(unit.path(), declared, used));
        if (keyFileNames.isEmpty()) {
            return;
        }
        for (Expression expression : unit.findAll(Expression.class)) {
            if (!candidate(expression)) {
                continue;
            }
            Optional<String> text = unit.string(expression);
            if (text.isPresent() && keyFileNames.contains(text.get())) {
                references.add(new Reference(unit.path(), unit.location() == LocationKind.TEST_CODE, text.get(), calledTypes(expression)));
            }
        }
    }

    Linking resolve(List<Observation> observations) {
        Map<RelativePath, Map<UsageContext, Integer>> votes = new HashMap<>();
        Map<RelativePath, Map<AlgorithmFamily, Set<Integer>>> sizes = new HashMap<>();
        for (Reference reference : references) {
            Optional<PemFacts> key = pem.byBasename(reference.fileName());
            if (key.isEmpty()) {
                continue;
            }
            Optional<AlgorithmFamily> family = key.get().family();
            Set<RelativePath> owners = owners(reference);
            Map<UsageContext, Integer> usageVotes = votes.computeIfAbsent(key.get().file(), k -> new EnumMap<>(UsageContext.class));
            for (Observation observation : observations) {
                boolean testCode = observation.evidence().locationKind() == LocationKind.TEST_CODE;
                boolean owned = owners.contains(observation.evidence().file()) && observation.role() == Role.FINDING
                        && observation.usage() != UsageContext.UNKNOWN && (reference.fromTestCode() || !testCode);
                boolean sameFamily = family.isEmpty() || observation.algorithm().family() == family.get();
                if (owned && sameFamily) {
                    usageVotes.merge(observation.usage(), 1, Integer::sum);
                    key.get().keySizeBits().ifPresent(size -> sizes.computeIfAbsent(observation.evidence().file(), k -> new EnumMap<>(AlgorithmFamily.class))
                            .computeIfAbsent(observation.algorithm().family(), k -> new TreeSet<>()).add(size));
                }
            }
        }
        Map<RelativePath, UsageContext> decided = new HashMap<>();
        votes.forEach((file, counts) -> decide(counts).ifPresent(usage -> decided.put(file, usage)));
        shareWithCounterparts(decided);
        return new Linking(decided, sizes);
    }

    /** The two halves of a key pair are used for the same thing: a half the code never loads takes the other's usage. */
    private void shareWithCounterparts(Map<RelativePath, UsageContext> decided) {
        for (PemFacts key : pem.all()) {
            if (key.role() != PemRole.PRIVATE_KEY) {
                continue;
            }
            pem.counterpart(key.file()).filter(c -> c.role() == PemRole.PUBLIC_KEY).ifPresent(half -> {
                UsageContext own = decided.get(key.file());
                UsageContext other = decided.get(half.file());
                if (own == null && other != null) {
                    decided.put(key.file(), other);
                } else if (other == null && own != null) {
                    decided.put(half.file(), own);
                }
            });
        }
    }

    private Set<RelativePath> owners(Reference reference) {
        String module = module(reference.from());
        Set<RelativePath> owners = new LinkedHashSet<>();
        for (String type : reference.calledTypes()) {
            for (UnitFacts unit : units) {
                boolean related = unit.declaredTypes().contains(type) || unit.usedTypes().contains(type);
                if (related && module(unit.file()).equals(module)) {
                    owners.add(unit.file());
                }
            }
        }
        if (owners.isEmpty()) {
            owners.add(reference.from());
        }
        return owners;
    }

    private String module(RelativePath file) {
        String value = file.value();
        int marker = value.indexOf("/src/");
        if (value.startsWith("src/")) {
            return "";
        }
        return marker < 0 ? "" : value.substring(0, marker);
    }

    private static Optional<UsageContext> decide(Map<UsageContext, Integer> counts) {
        int best = counts.values().stream().mapToInt(Integer::intValue).max().orElse(0);
        List<UsageContext> leaders = counts.entrySet().stream().filter(e -> e.getValue() == best && best > 0).map(Map.Entry::getKey).toList();
        return leaders.size() == 1 ? Optional.of(leaders.get(0)) : Optional.empty();
    }

    private static boolean candidate(Expression expression) {
        boolean kind = expression instanceof StringLiteralExpr || expression instanceof NameExpr || expression instanceof FieldAccessExpr
                || (expression instanceof BinaryExpr binary && binary.getOperator() == BinaryExpr.Operator.PLUS);
        if (!kind) {
            return false;
        }
        Optional<Node> parent = expression.getParentNode();
        boolean insideConcatenation = parent.filter(p -> p instanceof BinaryExpr binary && binary.getOperator() == BinaryExpr.Operator.PLUS).isPresent();
        boolean declaration = parent.filter(VariableDeclarator.class::isInstance).isPresent();
        return !insideConcatenation && !declaration;
    }

    private static Set<String> calledTypes(Expression start) {
        Set<String> types = new LinkedHashSet<>();
        Node child = start;
        while (child.getParentNode().isPresent()) {
            Node parent = child.getParentNode().get();
            Node current = child;
            if (parent instanceof MethodCallExpr call && call.getArguments().stream().anyMatch(a -> a == current)) {
                call.getScope().map(JavaUnit::simpleName).filter(name -> !name.isEmpty() && Character.isUpperCase(name.charAt(0)))
                        .ifPresent(types::add);
            } else if (parent instanceof ObjectCreationExpr creation && creation.getArguments().stream().anyMatch(a -> a == current)) {
                types.add(creation.getType().getNameAsString());
            } else if (parent instanceof Statement || parent instanceof BodyDeclaration<?>) {
                break;
            }
            child = parent;
        }
        return types;
    }

    private static String simpleType(String type) {
        String base = type.contains("<") ? type.substring(0, type.indexOf('<')) : type;
        base = base.replace("[]", "").replace("...", "").strip();
        int dot = base.lastIndexOf('.');
        return dot < 0 ? base : base.substring(dot + 1);
    }
}
