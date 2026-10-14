package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.CryptoDetector;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.DetectionSink;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileKind;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.FileSupport;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectFile;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemFacts;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemRole;
import java.util.Optional;

/**
 * PEM files: an X.509 certificate gives its public key algorithm, size and signature algorithm; a public key gives
 * algorithm and size; a private key is recognised by its header only and is never decoded (D-19). A private key next to a
 * certificate of the same name belongs to that certificate; any other key file gets its usage from the code that loads it
 * (D-185), which the plugin fills in later.
 */
public final class PemCertificateScanner implements CryptoDetector {

    public static final String ID = "pem.certificate";

    private final CanonicalNames names;

    public PemCertificateScanner(CanonicalNames names) {
        this.names = names;
    }

    @Override
    public String detectorId() {
        return ID;
    }

    @Override
    public boolean appliesTo(ProjectFile file) {
        return file.kind() == FileKind.PEM;
    }

    @Override
    public void detect(ProjectIndex index, FileContext context, DetectionSink sink) {
        ProjectFile file = context.file();
        Optional<PemFacts> found = index.pem().get(file.path());
        if (found.isEmpty() || found.get().role() == PemRole.OTHER) {
            return;
        }
        PemFacts facts = found.get();
        AlgorithmFamily family = facts.family().orElse(AlgorithmFamily.UNKNOWN);
        switch (facts.role()) {
            case CERTIFICATE -> certificate(file, facts, family, sink);
            case PUBLIC_KEY -> sink.add(FileSupport.wholeFile(file, algorithm(family, "PUBLIC KEY", facts), UsageContext.UNKNOWN, 0.5, ID, null)
                    .fromLoader());
            case PRIVATE_KEY -> privateKey(index, file, facts, family, sink);
            default -> {
            }
        }
    }

    private void certificate(ProjectFile file, PemFacts facts, AlgorithmFamily family, DetectionSink sink) {
        String signature = facts.signature().map(CryptoAlgorithm::rawName).orElse("unknown signature");
        double confidence = family == AlgorithmFamily.UNKNOWN ? 0.4 : 0.95;
        sink.add(FileSupport.wholeFile(file, algorithm(family, "X.509 " + signature, facts), UsageContext.CERTIFICATE, confidence, ID, null));
        facts.signature().flatMap(s -> s.hash()).filter(h -> h.equals("MD5") || h.equals("SHA-1"))
                .flatMap(h -> names.algorithm(CanonicalKind.HASH, h)).ifPresent(hash -> sink.add(FileSupport.wholeFile(file,
                        new CryptoAlgorithm(hash.family(), "X.509 " + signature, Optional.empty(), Optional.empty(), hash.hash(), Optional.empty()),
                        UsageContext.CERTIFICATE, 0.95, ID, null)));
    }

    private void privateKey(ProjectIndex index, ProjectFile file, PemFacts facts, AlgorithmFamily family, DetectionSink sink) {
        CryptoAlgorithm algorithm = algorithm(family, facts.label(), facts);
        Optional<PemFacts> counterpart = index.pem().counterpart(file.path());
        Observation observation = FileSupport.wholeFile(file, algorithm, UsageContext.CERTIFICATE, 0.7, ID, null);
        if (counterpart.isPresent() && counterpart.get().role() == PemRole.CERTIFICATE) {
            sink.add(observation);
        } else {
            sink.add(observation.withUsage(UsageContext.UNKNOWN).withConfidence(0.5).fromLoader());
        }
    }

    private static CryptoAlgorithm algorithm(AlgorithmFamily family, String rawName, PemFacts facts) {
        return new CryptoAlgorithm(family, rawName, Optional.empty(), Optional.empty(), Optional.empty(), facts.keySizeBits());
    }
}
