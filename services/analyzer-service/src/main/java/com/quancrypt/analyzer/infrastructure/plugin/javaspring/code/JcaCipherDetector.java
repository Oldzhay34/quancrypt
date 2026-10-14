package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

import com.github.javaparser.ast.expr.MethodCallExpr;
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
import java.util.Set;

/**
 * {@code Cipher.getInstance("ALG/MODE/PADDING")}: splits the transformation into family, mode and padding with the canonical
 * dictionary. RSA's "ECB" is a name leftover and becomes mode NONE (crypto-domain); a block cipher without a mode runs in
 * ECB in the JDK, reported at a lower confidence (D-189).
 */
public final class JcaCipherDetector implements CryptoDetector {

    public static final String ID = "jca.cipher";
    private static final String LIBRARY = "JCA";

    private final CanonicalNames names;

    public JcaCipherDetector(CanonicalNames names) {
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
        if (!unit.refersTo("Cipher", "javax.crypto.Cipher")) {
            return;
        }
        for (MethodCallExpr call : unit.calls("Cipher", "getInstance")) {
            if (call.getArguments().isEmpty()) {
                continue;
            }
            Optional<String> raw = unit.string(call.getArgument(0));
            if (raw.isEmpty()) {
                sink.add(CodeSupport.observation(unit, call, CodeSupport.unknown("Cipher.getInstance:unresolved"), UsageContext.UNKNOWN,
                        0.3, ID, LIBRARY));
                continue;
            }
            Optional<CryptoAlgorithm> algorithm = names.transformation(raw.get());
            if (algorithm.isEmpty()) {
                sink.unresolved(ID, raw.get());
                sink.add(CodeSupport.observation(unit, call, CodeSupport.unknown(raw.get()), UsageContext.UNKNOWN, 0.3, ID, LIBRARY));
                continue;
            }
            CryptoAlgorithm found = algorithm.get();
            boolean wrapping = found.rawName().equalsIgnoreCase("AESWrap")
                    || CodeSupport.mentionsConstant(call, "Cipher", Set.of("WRAP_MODE", "UNWRAP_MODE"));
            UsageContext usage = wrapping ? UsageContext.KEY_WRAP
                    : found.family().isQuantumVulnerable() ? UsageContext.ENCRYPTION : UsageContext.SYMMETRIC_ENCRYPTION;
            double confidence = raw.get().contains("/") ? 0.9 : 0.7;
            sink.add(CodeSupport.observation(unit, call, found, usage, confidence, ID, LIBRARY));
        }
    }
}
