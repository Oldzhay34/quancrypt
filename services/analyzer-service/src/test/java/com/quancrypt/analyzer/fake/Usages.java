package com.quancrypt.analyzer.fake;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LineRange;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.Optional;

/** Builders of sample crypto usages for tests. */
public final class Usages {

    private Usages() {
    }

    public static CryptoUsage rsaEncryption(String file, LocationKind kind) {
        return new CryptoUsage(new Evidence(RelativePath.of(file), Optional.of(new LineRange(10, 12)), kind), "Card#encrypt",
                new CryptoAlgorithm(AlgorithmFamily.RSA, "RSA/ECB/OAEPWithSHA-256AndMGF1Padding", Optional.of("ECB"),
                        Optional.of("OAEPWithSHA-256AndMGF1Padding"), Optional.of("SHA-256"), Optional.of(2048)),
                UsageContext.ENCRYPTION, Priority.P1, Optional.of("JCA"), 0.9, "java.cipher");
    }

    public static CryptoUsage certificateFile(String file) {
        return new CryptoUsage(new Evidence(RelativePath.of(file), Optional.empty(), LocationKind.CERTIFICATE_FILE), file,
                new CryptoAlgorithm(AlgorithmFamily.RSA, "rsaEncryption", Optional.empty(), Optional.empty(), Optional.empty(),
                        Optional.empty()),
                UsageContext.CERTIFICATE, Priority.P3, Optional.empty(), 1.0, "pem.certificate");
    }
}
