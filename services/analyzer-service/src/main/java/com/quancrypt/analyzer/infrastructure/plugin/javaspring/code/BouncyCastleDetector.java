package com.quancrypt.analyzer.infrastructure.plugin.javaspring.code;

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
import java.util.Map;
import java.util.Optional;

/**
 * Bouncy Castle's own (lightweight) crypto classes in files that import {@code org.bouncycastle}: engines, signers and
 * agreements are looked up in a table, {@code JcaContentSignerBuilder("SHA256withRSA")} through the dictionary. Calls
 * through the JCA ("RSA", "BC") are seen by the JCA detectors.
 */
public final class BouncyCastleDetector implements CryptoDetector {

    public static final String ID = "bouncycastle";
    private static final String LIBRARY = "BouncyCastle";

    private record Known(AlgorithmFamily family, UsageContext usage, String padding, double confidence) {
    }

    private static final Map<String, Known> CLASSES = Map.ofEntries(
            Map.entry("RSAEngine", new Known(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, null, 0.6)),
            Map.entry("PKCS1Encoding", new Known(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, "PKCS1_V1_5", 0.7)),
            Map.entry("OAEPEncoding", new Known(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, "OAEP", 0.7)),
            Map.entry("RSADigestSigner", new Known(AlgorithmFamily.RSA, UsageContext.SIGNATURE, null, 0.8)),
            Map.entry("PSSSigner", new Known(AlgorithmFamily.RSA, UsageContext.SIGNATURE, "PSS", 0.8)),
            Map.entry("ECDSASigner", new Known(AlgorithmFamily.ECDSA, UsageContext.SIGNATURE, null, 0.8)),
            Map.entry("Ed25519Signer", new Known(AlgorithmFamily.EDDSA, UsageContext.SIGNATURE, null, 0.8)),
            Map.entry("Ed448Signer", new Known(AlgorithmFamily.EDDSA, UsageContext.SIGNATURE, null, 0.8)),
            Map.entry("ECDHBasicAgreement", new Known(AlgorithmFamily.ECDH, UsageContext.KEY_AGREEMENT, null, 0.8)),
            Map.entry("ECDHCBasicAgreement", new Known(AlgorithmFamily.ECDH, UsageContext.KEY_AGREEMENT, null, 0.8)),
            Map.entry("X25519Agreement", new Known(AlgorithmFamily.X25519, UsageContext.KEY_AGREEMENT, null, 0.8)),
            Map.entry("DHBasicAgreement", new Known(AlgorithmFamily.DH, UsageContext.KEY_AGREEMENT, null, 0.8)),
            Map.entry("DESEngine", new Known(AlgorithmFamily.DES, UsageContext.SYMMETRIC_ENCRYPTION, null, 0.8)),
            Map.entry("DESedeEngine", new Known(AlgorithmFamily.TRIPLE_DES, UsageContext.SYMMETRIC_ENCRYPTION, null, 0.8)));

    private final CanonicalNames names;

    public BouncyCastleDetector(CanonicalNames names) {
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
        if (!unit.importsPackage("org.bouncycastle")) {
            return;
        }
        for (ObjectCreationExpr creation : unit.findAll(ObjectCreationExpr.class)) {
            String type = creation.getType().getNameAsString();
            Known known = CLASSES.get(type);
            if (known != null) {
                CryptoAlgorithm algorithm = new CryptoAlgorithm(known.family(), type, Optional.empty(), Optional.ofNullable(known.padding()),
                        Optional.empty(), Optional.empty());
                sink.add(CodeSupport.observation(unit, creation, algorithm, known.usage(), known.confidence(), ID, LIBRARY));
            } else if (type.equals("JcaContentSignerBuilder") && !creation.getArguments().isEmpty()) {
                signer(unit, creation, sink);
            } else if (type.equals("RSAKeyGenerationParameters") && creation.getArguments().size() >= 3) {
                keyGeneration(unit, creation, sink);
            }
        }
    }

    private void signer(JavaUnit unit, ObjectCreationExpr creation, DetectionSink sink) {
        Optional<String> raw = unit.string(creation.getArgument(0));
        if (raw.isEmpty()) {
            return;
        }
        Optional<CryptoAlgorithm> algorithm = names.algorithm(CanonicalKind.SIGNATURE, raw.get());
        if (algorithm.isEmpty()) {
            sink.unresolved(ID, raw.get());
            return;
        }
        sink.add(CodeSupport.observation(unit, creation, algorithm.get(), UsageContext.SIGNATURE, 0.9, ID, LIBRARY));
        algorithm.get().hash().filter(h -> h.equals("MD5") || h.equals("SHA-1")).flatMap(h -> names.algorithm(CanonicalKind.HASH, h))
                .ifPresent(hash -> sink.add(CodeSupport.observation(unit, creation,
                        new CryptoAlgorithm(hash.family(), raw.get(), Optional.empty(), Optional.empty(), hash.hash(), Optional.empty()),
                        UsageContext.SIGNATURE, 0.9, ID, LIBRARY)));
    }

    private void keyGeneration(JavaUnit unit, ObjectCreationExpr creation, DetectionSink sink) {
        Optional<Integer> strength = unit.integer(creation.getArgument(2));
        CryptoAlgorithm algorithm = new CryptoAlgorithm(AlgorithmFamily.RSA, "RSAKeyGenerationParameters", Optional.empty(),
                Optional.empty(), Optional.empty(), strength);
        boolean weak = strength.filter(bits -> bits < PriorityClassifier.MIN_SAFE_RSA_BITS).isPresent();
        Observation observation = CodeSupport.observation(unit, creation, algorithm, UsageContext.UNKNOWN, 0.5, ID, LIBRARY);
        sink.add(observation.withRole(weak ? Role.FINDING : Role.FALLBACK));
    }
}
