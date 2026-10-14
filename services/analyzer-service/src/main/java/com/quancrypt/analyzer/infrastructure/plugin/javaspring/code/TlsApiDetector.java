package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.BodyDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.BooleanLiteralExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.LambdaExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.stmt.ReturnStmt;
import com.github.javaparser.ast.stmt.Statement;
import com.quancrypt.analyzer.domain.model.CanonicalEntry;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.TlsIdentity;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CodeSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaUnit;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * TLS in code: {@code SSLContext.getInstance(protocol)}, Spring Boot's {@code SslBundles.getBundle(name)} (the key
 * comes from the bundle's certificate) and the forbidden pattern signals of crypto-domain: a {@code TrustManager} that
 * trusts everything and a {@code HostnameVerifier} that always says yes (D-188: family UNKNOWN, TLS_SERVER_AUTH, P0).
 */
public final class TlsApiDetector implements CryptoDetector {

    public static final String ID = "java.tls-api";
    private static final String LIBRARY = "JSSE";
    private static final Set<String> TRUST_MANAGERS = Set.of("X509TrustManager", "TrustManager", "X509ExtendedTrustManager");
    private static final Set<String> HOSTNAME_VERIFIERS = Set.of("HostnameVerifier");
    private static final List<String[]> TRUST_ALL_CONSTANTS = List.of(
            new String[] {"InsecureTrustManagerFactory", "INSTANCE", "TrustManager:trust-all"},
            new String[] {"TrustAllStrategy", "INSTANCE", "TrustManager:trust-all"},
            new String[] {"NoopHostnameVerifier", "INSTANCE", "HostnameVerifier:allow-all"},
            new String[] {"SSLConnectionSocketFactory", "ALLOW_ALL_HOSTNAME_VERIFIER", "HostnameVerifier:allow-all"},
            new String[] {"SSLSocketFactory", "ALLOW_ALL_HOSTNAME_VERIFIER", "HostnameVerifier:allow-all"});

    private final CanonicalNames names;

    public TlsApiDetector(CanonicalNames names) {
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
        sslContexts(index, unit, sink);
        sslBundles(index, unit, sink);
        trustManagers(unit, sink);
        hostnameVerifiers(unit, sink);
        constants(unit, sink);
    }

    private void sslContexts(ProjectIndex index, JavaUnit unit, DetectionSink sink) {
        if (!unit.refersTo("SSLContext", "javax.net.ssl.SSLContext")) {
            return;
        }
        for (MethodCallExpr call : unit.calls("SSLContext", "getInstance")) {
            Optional<String> raw = CodeSupport.firstString(unit, call);
            if (raw.isEmpty()) {
                sink.add(CodeSupport.observation(unit, call, CodeSupport.unknown("SSLContext.getInstance:unresolved"),
                        UsageContext.TLS_KEY_EXCHANGE, 0.3, ID, LIBRARY));
                continue;
            }
            Optional<CanonicalEntry> protocol = names.entry(CanonicalKind.TLS_PROTOCOL, raw.get());
            if (protocol.isEmpty()) {
                sink.unresolved(ID, raw.get());
            }
            TlsIdentity identity = index.defaultIdentity();
            sink.add(CodeSupport.tls(unit, call, identity, "SSLContext:" + CodeSupport.nameShaped(raw.get()), protocol.flatMap(CanonicalEntry::mode).orElse(null),
                    ID, LIBRARY));
        }
    }

    private void sslBundles(ProjectIndex index, JavaUnit unit, DetectionSink sink) {
        if (!unit.importsPackage("org.springframework.boot.ssl")) {
            return;
        }
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            if (call.getNameAsString().equals("getBundle") && call.getArguments().size() == 1) {
                Optional<String> bundle = unit.string(call.getArgument(0));
                TlsIdentity identity = bundle.map(index::identityOf).orElseGet(index::defaultIdentity);
                sink.add(CodeSupport.tls(unit, call, identity, "SslBundle", null, ID, "spring-boot"));
            }
        }
    }

    private void trustManagers(JavaUnit unit, DetectionSink sink) {
        for (ClassOrInterfaceDeclaration declaration : unit.findAll(ClassOrInterfaceDeclaration.class)) {
            boolean trust = declaration.getImplementedTypes().stream().anyMatch(t -> TRUST_MANAGERS.contains(t.getNameAsString()))
                    || declaration.getExtendedTypes().stream().anyMatch(t -> TRUST_MANAGERS.contains(t.getNameAsString()));
            if (trust) {
                members(declaration.getMembers(), "checkServerTrusted").stream().filter(TlsApiDetector::emptyBody)
                        .forEach(method -> trustAll(unit, method, "TrustManager:trust-all", sink));
            }
        }
        for (ObjectCreationExpr creation : unit.findAll(ObjectCreationExpr.class)) {
            if (TRUST_MANAGERS.contains(creation.getType().getNameAsString()) && creation.getAnonymousClassBody().isPresent()) {
                members(creation.getAnonymousClassBody().get(), "checkServerTrusted").stream().filter(TlsApiDetector::emptyBody)
                        .forEach(method -> trustAll(unit, method, "TrustManager:trust-all", sink));
            }
        }
    }

    private void hostnameVerifiers(JavaUnit unit, DetectionSink sink) {
        for (ClassOrInterfaceDeclaration declaration : unit.findAll(ClassOrInterfaceDeclaration.class)) {
            if (declaration.getImplementedTypes().stream().anyMatch(t -> HOSTNAME_VERIFIERS.contains(t.getNameAsString()))) {
                members(declaration.getMembers(), "verify").stream().filter(TlsApiDetector::returnsTrue)
                        .forEach(method -> trustAll(unit, method, "HostnameVerifier:allow-all", sink));
            }
        }
        for (ObjectCreationExpr creation : unit.findAll(ObjectCreationExpr.class)) {
            if (HOSTNAME_VERIFIERS.contains(creation.getType().getNameAsString()) && creation.getAnonymousClassBody().isPresent()) {
                members(creation.getAnonymousClassBody().get(), "verify").stream().filter(TlsApiDetector::returnsTrue)
                        .forEach(method -> trustAll(unit, method, "HostnameVerifier:allow-all", sink));
            }
        }
        for (LambdaExpr lambda : unit.findAll(LambdaExpr.class)) {
            boolean verifierArgument = lambda.getParentNode().filter(parent -> parent instanceof MethodCallExpr call
                    && call.getNameAsString().contains("ostnameVerifier")).isPresent();
            if (verifierArgument && alwaysTrue(lambda)) {
                trustAll(unit, lambda, "HostnameVerifier:allow-all", sink);
            }
        }
    }

    private void constants(JavaUnit unit, DetectionSink sink) {
        for (FieldAccessExpr access : unit.findAll(FieldAccessExpr.class)) {
            for (String[] constant : TRUST_ALL_CONSTANTS) {
                if (access.getNameAsString().equals(constant[1]) && JavaUnit.simpleName(access.getScope()).equals(constant[0])) {
                    trustAll(unit, access, constant[2], sink);
                }
            }
        }
    }

    private static void trustAll(JavaUnit unit, Node node, String label, DetectionSink sink) {
        sink.add(CodeSupport.observation(unit, node, CodeSupport.unknown(label), UsageContext.TLS_SERVER_AUTH, 0.9, ID, LIBRARY)
                .withPriority(Priority.P0));
    }

    private static List<MethodDeclaration> members(List<BodyDeclaration<?>> members, String name) {
        return members.stream().filter(MethodDeclaration.class::isInstance).map(MethodDeclaration.class::cast)
                .filter(method -> method.getNameAsString().equals(name)).toList();
    }

    private static boolean emptyBody(MethodDeclaration method) {
        return method.getBody().map(body -> body.getStatements().isEmpty()).orElse(false);
    }

    private static boolean returnsTrue(MethodDeclaration method) {
        return method.getBody().filter(body -> body.getStatements().size() == 1).map(body -> isReturnTrue(body.getStatement(0))).orElse(false);
    }

    private static boolean alwaysTrue(LambdaExpr lambda) {
        Statement body = lambda.getBody();
        if (body.isExpressionStmt()) {
            return isTrue(body.asExpressionStmt().getExpression());
        }
        return body.isBlockStmt() && body.asBlockStmt().getStatements().size() == 1 && isReturnTrue(body.asBlockStmt().getStatement(0));
    }

    private static boolean isReturnTrue(Statement statement) {
        return statement instanceof ReturnStmt returned && returned.getExpression().filter(TlsApiDetector::isTrue).isPresent();
    }

    private static boolean isTrue(Expression expression) {
        return expression instanceof BooleanLiteralExpr literal && literal.getValue();
    }
}
