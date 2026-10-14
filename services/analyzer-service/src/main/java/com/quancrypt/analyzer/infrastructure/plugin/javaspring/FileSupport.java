package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.Optional;

/** Helpers the file and configuration detectors share. */
public final class FileSupport {

    private FileSupport() {
    }

    /** An observation at one line of a file; the symbol is the configuration key. */
    public static Observation atLine(ProjectFile file, int line, String symbol, CryptoAlgorithm algorithm, UsageContext usage,
            double confidence, String detectorId, String library) {
        Evidence evidence = new Evidence(file.path(), line > 0 ? Optional.of(new LineRange(line, line)) : Optional.empty(), file.location());
        return Observation.finding(evidence, NameSanitizer.clean(symbol), algorithm, usage, confidence, detectorId, library);
    }

    /** An observation about the whole file (a certificate, a key, a keystore); the symbol is the file name. */
    public static Observation wholeFile(ProjectFile file, CryptoAlgorithm algorithm, UsageContext usage, double confidence,
            String detectorId, String library) {
        Evidence evidence = new Evidence(file.path(), Optional.empty(), file.location());
        return Observation.finding(evidence, NameSanitizer.clean(file.name()), algorithm, usage, confidence, detectorId, library);
    }

    /** A TLS connection configured in a file: the key comes from the identity (bundle certificate or project default). */
    public static Observation tls(ProjectFile file, int line, String symbol, TlsIdentity identity, String rawName, String mode,
            String detectorId, String library) {
        return atLine(file, line, symbol, identity.algorithm(NameSanitizer.clean(rawName), mode), UsageContext.TLS_KEY_EXCHANGE,
                identity.confidence(), detectorId, library);
    }

    /** The identity as a certificate-bearing usage (mutual TLS, server certificate): same key, another context. */
    public static Observation identityUsage(ProjectFile file, int line, String symbol, TlsIdentity identity, String rawName,
            UsageContext usage, String detectorId, String library) {
        return atLine(file, line, symbol, identity.algorithm(NameSanitizer.clean(rawName), null), usage, identity.confidence(), detectorId,
                library);
    }
}
