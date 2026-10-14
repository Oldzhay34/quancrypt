package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

import com.github.javaparser.ast.expr.MethodCallExpr;
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
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Role;
import java.util.Optional;

/**
 * {@code KeyFactory.getInstance("RSA")}: a key loader only builds a key object, the usage lives in the code that signs,
 * encrypts or opens a connection with it (D-112). It is a supporting observation and never a finding by itself.
 */
public final class JcaKeyFactoryDetector implements CryptoDetector {

    public static final String ID = "jca.keyfactory";
    private static final String LIBRARY = "JCA";

    private final CanonicalNames names;

    public JcaKeyFactoryDetector(CanonicalNames names) {
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
        if (!unit.refersTo("KeyFactory", "java.security.KeyFactory")) {
            return;
        }
        for (MethodCallExpr call : unit.calls("KeyFactory", "getInstance")) {
            Optional<String> raw = CodeSupport.firstString(unit, call);
            Optional<CryptoAlgorithm> algorithm = raw.flatMap(r -> names.algorithm(CanonicalKind.ALGORITHM, r))
                    .filter(a -> a.family() != AlgorithmFamily.UNKNOWN);
            algorithm.ifPresent(a -> sink.add(CodeSupport.observation(unit, call, a, UsageContext.UNKNOWN, 0.5, ID, LIBRARY)
                    .withRole(Role.SUPPORT)));
        }
    }
}
