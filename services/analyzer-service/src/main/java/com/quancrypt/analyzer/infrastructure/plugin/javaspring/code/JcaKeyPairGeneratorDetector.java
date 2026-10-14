package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.domain.policy.PriorityClassifier;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CodeSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Role;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * {@code KeyPairGenerator.getInstance("RSA")} with the key size of the {@code initialize(n)} call or of an
 * {@code RSAKeyGenParameterSpec} / {@code ECGenParameterSpec} next to it. A generated key says what the key is, not what
 * it is used for: it is reported only when the file has no other finding of the family, or when the key is weak (D-190c);
 * otherwise it only lends its key size to the findings of the file.
 */
public final class JcaKeyPairGeneratorDetector implements CryptoDetector {

    public static final String ID = "jca.keypairgenerator";
    private static final String LIBRARY = "JCA";
    private static final Pattern CURVE_BITS = Pattern.compile("(?:secp|sect|prime|P-?)(\\d{3})");

    private final CanonicalNames names;

    public JcaKeyPairGeneratorDetector(CanonicalNames names) {
        this.names = names;
    }

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public boolean appliesTo(ProjectFile file) {
        return file.kind() == FileKind.JAVA;
    }

    @Override
    public void detect(ProjectIndex index, FileContext context, DetectionSink sink) {
        JavaUnit unit = context.java();
        if (!unit.refersTo("KeyPairGenerator", "java.security.KeyPairGenerator")) {
            return;
        }
        for (MethodCallExpr call : unit.calls("KeyPairGenerator", "getInstance")) {
            Optional<String> raw = CodeSupport.firstString(unit, call);
            if (raw.isEmpty()) {
                continue;
            }
            Optional<CryptoAlgorithm> algorithm = names.algorithm(CanonicalKind.ALGORITHM, raw.get());
            if (algorithm.isEmpty() || algorithm.get().family() == AlgorithmFamily.UNKNOWN) {
                sink.unresolved(ID, raw.get());
                continue;
            }
            Optional<Integer> size = keySize(unit, call);
            CryptoAlgorithm sized = new CryptoAlgorithm(algorithm.get().family(), algorithm.get().rawName(), Optional.empty(),
                    Optional.empty(), Optional.empty(), size.or(() -> algorithm.get().keySizeBits()));
            boolean weak = size.filter(bits -> bits < PriorityClassifier.MIN_SAFE_RSA_BITS).isPresent()
                    && (sized.family() == AlgorithmFamily.RSA || sized.family() == AlgorithmFamily.DSA);
            Observation observation = CodeSupport.observation(unit, call, sized, UsageContext.UNKNOWN, 0.5, ID, LIBRARY);
            sink.add(observation.withRole(weak ? Role.FINDING : Role.FALLBACK));
        }
    }

    private Optional<Integer> keySize(JavaUnit unit, MethodCallExpr generator) {
        Node scope = generator;
        while (!(scope instanceof CallableDeclaration<?>) && scope.getParentNode().isPresent()) {
            scope = scope.getParentNode().get();
        }
        for (MethodCallExpr initialize : scope.findAll(MethodCallExpr.class)) {
            if (!initialize.getNameAsString().equals("initialize") || initialize.getArguments().isEmpty()) {
                continue;
            }
            Expression argument = initialize.getArgument(0);
            Optional<Integer> direct = unit.integer(argument);
            if (direct.isPresent()) {
                return direct;
            }
            if (argument instanceof ObjectCreationExpr creation) {
                Optional<Integer> fromSpec = fromSpec(unit, creation);
                if (fromSpec.isPresent()) {
                    return fromSpec;
                }
            }
        }
        return Optional.empty();
    }

    private Optional<Integer> fromSpec(JavaUnit unit, ObjectCreationExpr creation) {
        String type = creation.getType().getNameAsString();
        if (creation.getArguments().isEmpty()) {
            return Optional.empty();
        }
        if (type.equals("RSAKeyGenParameterSpec")) {
            return unit.integer(creation.getArgument(0));
        }
        if (type.equals("ECGenParameterSpec")) {
            return unit.string(creation.getArgument(0)).flatMap(JcaKeyPairGeneratorDetector::curveBits);
        }
        return Optional.empty();
    }

    private static Optional<Integer> curveBits(String curve) {
        Matcher matcher = CURVE_BITS.matcher(curve);
        return matcher.find() ? Optional.of(Integer.parseInt(matcher.group(1))) : Optional.empty();
    }
}
