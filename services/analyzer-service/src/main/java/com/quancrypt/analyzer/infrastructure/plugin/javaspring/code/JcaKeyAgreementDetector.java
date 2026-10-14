package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

import com.github.javaparser.ast.expr.MethodCallExpr;
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
import java.util.Optional;

/** {@code KeyAgreement.getInstance("ECDH")}: Diffie-Hellman style key agreement (ECDH, DH, X25519), the key establishment of the table. */
public final class JcaKeyAgreementDetector implements CryptoDetector {

    public static final String ID = "jca.keyagreement";
    private static final String LIBRARY = "JCA";

    private final CanonicalNames names;

    public JcaKeyAgreementDetector(CanonicalNames names) {
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
        if (!unit.refersTo("KeyAgreement", "javax.crypto.KeyAgreement")) {
            return;
        }
        for (MethodCallExpr call : unit.calls("KeyAgreement", "getInstance")) {
            Optional<String> raw = CodeSupport.firstString(unit, call);
            if (raw.isEmpty()) {
                sink.add(CodeSupport.observation(unit, call, CodeSupport.unknown("KeyAgreement.getInstance:unresolved"), UsageContext.KEY_AGREEMENT,
                        0.3, ID, LIBRARY));
                continue;
            }
            Optional<CryptoAlgorithm> algorithm = names.algorithm(CanonicalKind.ALGORITHM, raw.get());
            if (algorithm.isEmpty()) {
                sink.unresolved(ID, raw.get());
                sink.add(CodeSupport.observation(unit, call, CodeSupport.unknown(raw.get()), UsageContext.KEY_AGREEMENT, 0.3, ID, LIBRARY));
                continue;
            }
            sink.add(CodeSupport.observation(unit, call, algorithm.get(), UsageContext.KEY_AGREEMENT, 0.9, ID, LIBRARY));
        }
    }
}
