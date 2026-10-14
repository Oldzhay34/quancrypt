package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.github.javaparser.ast.DataKey;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/** Helpers the code detectors share: building observations and looking around a node. */
public final class CodeSupport {

    private static final DataKey<List<FieldAccessExpr>> ACCESSES = new DataKey<>() {
    };
    private static final Pattern NAME_SHAPE = Pattern.compile("[A-Za-z0-9._/+()#:-]{1,128}");

    private CodeSupport() {
    }

    /**
     * An algorithm of unknown family. The raw text is kept only when it has the shape of an algorithm name; anything else
     * (a sentence, a value that may hold a secret) is replaced by a label (D-190e).
     */
    public static CryptoAlgorithm unknown(String rawName) {
        return new CryptoAlgorithm(AlgorithmFamily.UNKNOWN, NameSanitizer.clean(nameShaped(rawName)), Optional.empty(), Optional.empty(),
                Optional.empty(), Optional.empty());
    }

    /** The text when it has the shape of a name (an algorithm, a protocol, a bundle), otherwise {@code unrecognized}. */
    public static String nameShaped(String text) {
        return NAME_SHAPE.matcher(text).matches() ? text : "unrecognized";
    }

    public static Observation observation(JavaUnit unit, Node node, CryptoAlgorithm algorithm, UsageContext usage, double confidence,
            String detectorId, String library) {
        return Observation.finding(unit.evidence(node), unit.symbol(node), algorithm, usage, confidence, detectorId, library);
    }

    /** The observation of a TLS connection: the key comes from the identity (bundle certificate or project default). */
    public static Observation tls(JavaUnit unit, Node node, TlsIdentity identity, String rawName, String mode, String detectorId,
            String library) {
        return observation(unit, node, identity.algorithm(NameSanitizer.clean(rawName), mode), UsageContext.TLS_KEY_EXCHANGE,
                identity.confidence(), detectorId, library);
    }

    /** Whether the declaration around the node (or the whole unit) mentions {@code Type.MEMBER} for one of the members. */
    public static boolean mentionsConstant(Node node, String typeName, Set<String> members) {
        Node declaration = node;
        while (!(declaration instanceof CallableDeclaration<?>) && declaration.getParentNode().isPresent()) {
            declaration = declaration.getParentNode().get();
        }
        List<FieldAccessExpr> accesses = declaration.containsData(ACCESSES) ? declaration.getData(ACCESSES) : null;
        if (accesses == null) {
            // Looked up once per declaration: every Cipher.getInstance of a long method asks, and a walk per call is quadratic.
            accesses = declaration.findAll(FieldAccessExpr.class);
            declaration.setData(ACCESSES, accesses);
        }
        return accesses.stream()
                .anyMatch(access -> members.contains(access.getNameAsString()) && JavaUnit.simpleName(access.getScope()).equals(typeName));
    }

    /** The first argument of a call as a string, when it can be resolved inside the unit. */
    public static Optional<String> firstString(JavaUnit unit, MethodCallExpr call) {
        return call.getArguments().isEmpty() ? Optional.empty() : unit.string(call.getArgument(0));
    }

    /** The library a JWT related import points at, for the finding's library field. */
    public static String jwtLibrary(JavaUnit unit) {
        if (unit.importsPackage("com.nimbusds")) {
            return "nimbus-jose-jwt";
        }
        if (unit.importsPackage("io.jsonwebtoken")) {
            return "jjwt";
        }
        if (unit.importsPackage("com.auth0.jwt")) {
            return "java-jwt";
        }
        if (unit.importsPackage("org.springframework.security.oauth2")) {
            return "spring-security-oauth2-jose";
        }
        return null;
    }
}
