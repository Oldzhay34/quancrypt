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

/**
 * {@code Signature.getInstance("SHA256withRSA")}: the public key algorithm, the hash and the padding come from the
 * dictionary. A signature over a broken hash (MD5, SHA-1) is also reported for the hash family, because the hash is the
 * weak part (D-190c).
 */
public final class JcaSignatureDetector implements CryptoDetector {

    public static final String ID = "jca.signature";
    private static final String LIBRARY = "JCA";

    private final CanonicalNames names;

    public JcaSignatureDetector(CanonicalNames names) {
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
        if (!unit.refersTo("Signature", "java.security.Signature")) {
            return;
        }
        for (MethodCallExpr call : unit.calls("Signature", "getInstance")) {
            Optional<String> raw = CodeSupport.firstString(unit, call);
            if (raw.isEmpty()) {
                sink.add(CodeSupport.observation(unit, call, CodeSupport.unknown("Signature.getInstance:unresolved"),
                        UsageContext.SIGNATURE, 0.3, ID, LIBRARY));
                continue;
            }
            Optional<CryptoAlgorithm> algorithm = names.algorithm(CanonicalKind.SIGNATURE, raw.get());
            if (algorithm.isEmpty()) {
                sink.unresolved(ID, raw.get());
                sink.add(CodeSupport.observation(unit, call, CodeSupport.unknown(raw.get()), UsageContext.SIGNATURE, 0.3, ID, LIBRARY));
                continue;
            }
            sink.add(CodeSupport.observation(unit, call, algorithm.get(), UsageContext.SIGNATURE, 0.9, ID, LIBRARY));
            weakHash(algorithm.get()).ifPresent(hash -> sink.add(CodeSupport.observation(unit, call, hash, UsageContext.SIGNATURE, 0.9,
                    ID, LIBRARY)));
        }
    }

    private Optional<CryptoAlgorithm> weakHash(CryptoAlgorithm signature) {
        return signature.hash().filter(h -> h.equals("MD5") || h.equals("SHA-1")).flatMap(h -> names.algorithm(CanonicalKind.HASH, h))
                .map(hash -> new CryptoAlgorithm(hash.family(), signature.rawName(), Optional.empty(), Optional.empty(), hash.hash(),
                        Optional.empty()));
    }
}
