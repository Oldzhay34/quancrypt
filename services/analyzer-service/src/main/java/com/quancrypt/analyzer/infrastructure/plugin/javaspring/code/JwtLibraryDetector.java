package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CodeSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * JWT signing in code: algorithm constants of nimbus-jose-jwt ({@code JWSAlgorithm.RS256}), jjwt ({@code SignatureAlgorithm},
 * {@code Jwts.SIG}), Spring Security ({@code SignatureAlgorithm}, {@code JwsAlgorithms}) and java-jwt
 * ({@code Algorithm.RSA256(..)}), signers and verifiers of nimbus, the documented RS256 default of Spring's
 * {@code NimbusJwtDecoder} builders, and algorithm names written as string literals ("RS256").
 */
public final class JwtLibraryDetector implements CryptoDetector {

    public static final String ID = "jwt.library";
    private static final Set<String> ALGORITHM_SCOPES = Set.of("JWSAlgorithm", "SignatureAlgorithm", "JwsAlgorithms", "SIG", "MacAlgorithm");
    private static final Set<String> LITERAL_ALGORITHMS = Set.of("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384",
            "ES512");
    private static final Set<String> DECODER_BUILDERS = Set.of("withJwkSetUri", "withPublicKey", "withIssuerLocation");
    private static final Set<String> ALGORITHM_SETTERS = Set.of("signatureAlgorithm", "jwsAlgorithm");
    private static final Map<String, AlgorithmFamily> NIMBUS_TYPES = Map.of(
            "RSASSASigner", AlgorithmFamily.RSA, "RSASSAVerifier", AlgorithmFamily.RSA, "RSAKey", AlgorithmFamily.RSA,
            "ECDSASigner", AlgorithmFamily.ECDSA, "ECDSAVerifier", AlgorithmFamily.ECDSA, "ECKey", AlgorithmFamily.ECDSA);

    private final CanonicalNames names;

    public JwtLibraryDetector(CanonicalNames names) {
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
        String library = CodeSupport.jwtLibrary(unit);
        if (library != null) {
            algorithmConstants(unit, library, sink);
            auth0(unit, library, sink);
            nimbusTypes(unit, library, sink);
            springDecoders(unit, library, sink);
        }
        literals(unit, library, sink);
    }

    private void algorithmConstants(JavaUnit unit, String library, DetectionSink sink) {
        for (FieldAccessExpr access : unit.findAll(FieldAccessExpr.class)) {
            if (ALGORITHM_SCOPES.contains(JavaUnit.simpleName(access.getScope()))) {
                algorithm(access.getNameAsString()).ifPresent(a -> sink.add(CodeSupport.observation(unit, access, a,
                        UsageContext.TOKEN_SIGNATURE, 0.9, ID, library)));
            }
        }
    }

    private void auth0(JavaUnit unit, String library, DetectionSink sink) {
        if (!unit.importsPackage("com.auth0.jwt")) {
            return;
        }
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            boolean onAlgorithm = call.getScope().filter(s -> JavaUnit.simpleName(s).equals("Algorithm")).isPresent();
            if (onAlgorithm) {
                algorithm(call.getNameAsString()).ifPresent(a -> sink.add(CodeSupport.observation(unit, call, a,
                        UsageContext.TOKEN_SIGNATURE, 0.9, ID, library)));
            }
        }
    }

    private void nimbusTypes(JavaUnit unit, String library, DetectionSink sink) {
        if (!unit.importsPackage("com.nimbusds")) {
            return;
        }
        for (ObjectCreationExpr creation : unit.findAll(ObjectCreationExpr.class)) {
            nimbus(unit, creation, creation.getType().getNameAsString(), library, sink);
        }
        for (ClassOrInterfaceType type : unit.findAll(ClassOrInterfaceType.class)) {
            if (type.getParentNode().filter(ObjectCreationExpr.class::isInstance).isEmpty()) {
                nimbus(unit, type, type.getNameAsString(), library, sink);
            }
        }
    }

    private void nimbus(JavaUnit unit, Node node, String type, String library, DetectionSink sink) {
        AlgorithmFamily family = NIMBUS_TYPES.get(type);
        if (family != null) {
            CryptoAlgorithm algorithm = new CryptoAlgorithm(family, type, Optional.empty(), Optional.empty(), Optional.empty(),
                    Optional.empty());
            sink.add(CodeSupport.observation(unit, node, algorithm, UsageContext.TOKEN_SIGNATURE, 0.7, ID, library));
        }
    }

    private void springDecoders(JavaUnit unit, String library, DetectionSink sink) {
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            boolean builder = DECODER_BUILDERS.contains(call.getNameAsString())
                    && call.getScope().filter(s -> JavaUnit.simpleName(s).equals("NimbusJwtDecoder")).isPresent();
            if (builder && !chainSetsAlgorithm(call)) {
                algorithm("RS256").ifPresent(a -> sink.add(CodeSupport.observation(unit, call, a, UsageContext.TOKEN_SIGNATURE, 0.6, ID,
                        library)));
            }
        }
    }

    private static boolean chainSetsAlgorithm(MethodCallExpr start) {
        Node current = start;
        while (current.getParentNode().isPresent()) {
            Node parent = current.getParentNode().get();
            Node child = current;
            if (parent instanceof MethodCallExpr outer && outer.getScope().filter(scope -> scope == child).isPresent()) {
                if (ALGORITHM_SETTERS.contains(outer.getNameAsString())) {
                    return true;
                }
                current = outer;
            } else {
                break;
            }
        }
        return false;
    }

    private void literals(JavaUnit unit, String library, DetectionSink sink) {
        for (StringLiteralExpr literal : unit.findAll(StringLiteralExpr.class)) {
            if (LITERAL_ALGORITHMS.contains(literal.asString())) {
                algorithm(literal.asString()).ifPresent(a -> sink.add(CodeSupport.observation(unit, literal, a,
                        UsageContext.TOKEN_SIGNATURE, 0.6, ID, library)));
            }
        }
    }

    private Optional<CryptoAlgorithm> algorithm(String name) {
        return names.algorithm(CanonicalKind.JWT_ALG, name);
    }
}
