package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
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
import java.util.regex.Pattern;

/**
 * MQTT over TLS with Eclipse Paho: {@code ssl://host:port} style broker URIs (a bare "ssl://" prefix check is not a
 * connection) and {@code setSocketFactory(..)} on the connect options. When the socket factory comes from a Spring SSL
 * bundle ({@code getBundle("name")}), the key is the bundle's certificate key.
 */
public final class MqttTlsDetector implements CryptoDetector {

    public static final String ID = "mqtt.tls";
    private static final String LIBRARY = "paho";
    private static final Pattern TLS_URI = Pattern.compile("^(ssl|tcps|wss|mqtts)://[^/\\s]");

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
        if (!unit.importsPackage("org.eclipse.paho")) {
            return;
        }
        for (MethodCallExpr call : unit.findAll(MethodCallExpr.class)) {
            if (call.getNameAsString().equals("setSocketFactory")) {
                sink.add(CodeSupport.tls(unit, call, identity(index, unit, call), "MqttConnectOptions.setSocketFactory", null, ID, LIBRARY));
            }
        }
        for (StringLiteralExpr literal : unit.findAll(StringLiteralExpr.class)) {
            if (TLS_URI.matcher(literal.asString()).lookingAt()) {
                String scheme = literal.asString().substring(0, literal.asString().indexOf("://") + 3);
                sink.add(CodeSupport.tls(unit, literal, index.defaultIdentity(), scheme, null, ID, LIBRARY));
            }
        }
    }

    private static TlsIdentity identity(ProjectIndex index, JavaUnit unit, MethodCallExpr call) {
        List<Expression> arguments = call.getArguments();
        for (Expression argument : arguments) {
            for (MethodCallExpr inner : argument.findAll(MethodCallExpr.class)) {
                if (inner.getNameAsString().equals("getBundle") && inner.getArguments().size() == 1) {
                    Optional<String> bundle = unit.string(inner.getArgument(0));
                    if (bundle.isPresent()) {
                        return index.identityOf(bundle.get());
                    }
                }
            }
        }
        return index.defaultIdentity();
    }
}
