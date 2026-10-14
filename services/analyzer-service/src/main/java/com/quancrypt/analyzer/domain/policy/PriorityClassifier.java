package com.quancrypt.analyzer.domain.policy;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.QuantumStatus;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.EnumSet;
import java.util.Set;

/**
 * Applies the crypto-domain priority table (P0 to P3) to a usage; the first matching rule wins (D-186). It is a port of
 * core-service's classifier (D-149, D-151) so the priority sent here is the one core-service accepts. Beyond core's
 * fields it also knows the block cipher mode and the RSA padding, which makes ECB and PKCS#1 v1.5 encryption P0; core
 * accepts a supplied P0 for AES and RSA for exactly this reason.
 */
public final class PriorityClassifier {

    public static final int MIN_SAFE_RSA_BITS = 2048;

    private static final Set<UsageContext> SIGNATURE_CONTEXTS = EnumSet.of(
            UsageContext.SIGNATURE, UsageContext.TOKEN_SIGNATURE, UsageContext.CERTIFICATE,
            UsageContext.TLS_SERVER_AUTH, UsageContext.MTLS_CLIENT_AUTH);
    private static final Set<UsageContext> KEY_ESTABLISHMENT = EnumSet.of(
            UsageContext.ENCRYPTION, UsageContext.KEY_WRAP, UsageContext.KEY_AGREEMENT);
    private static final Set<UsageContext> IDENTITY_AND_CERTIFICATES = EnumSet.of(
            UsageContext.TLS_SERVER_AUTH, UsageContext.MTLS_CLIENT_AUTH, UsageContext.CERTIFICATE);

    public PriorityVerdict classify(CryptoUsage usage) {
        CryptoAlgorithm algorithm = usage.algorithm();
        AlgorithmFamily family = algorithm.family();
        UsageContext context = usage.usageContext();
        if (weakClassic(usage)) {
            return new PriorityVerdict.Derived(Priority.P0);
        }
        if (context == UsageContext.KEYSTORE || usage.evidence().locationKind() == LocationKind.KEYSTORE_FILE) {
            return new PriorityVerdict.Derived(Priority.P3);
        }
        if (family == AlgorithmFamily.UNKNOWN || context == UsageContext.UNKNOWN) {
            return new PriorityVerdict.Undetermined();
        }
        QuantumStatus status = family.quantumStatus().orElseThrow();
        if (status != QuantumStatus.VULNERABLE) {
            return new PriorityVerdict.NotApplicable();
        }
        if (context == UsageContext.TLS_KEY_EXCHANGE || KEY_ESTABLISHMENT.contains(context)) {
            return new PriorityVerdict.Derived(Priority.P1);
        }
        if (context == UsageContext.SIGNATURE) {
            return new PriorityVerdict.Derived(Priority.P2);
        }
        if (context == UsageContext.TOKEN_SIGNATURE || IDENTITY_AND_CERTIFICATES.contains(context)) {
            return new PriorityVerdict.Derived(Priority.P3);
        }
        return new PriorityVerdict.Undetermined();
    }

    private static boolean weakClassic(CryptoUsage usage) {
        CryptoAlgorithm algorithm = usage.algorithm();
        AlgorithmFamily family = algorithm.family();
        boolean weakCipher = family == AlgorithmFamily.DES || family == AlgorithmFamily.TRIPLE_DES;
        boolean weakRsaKey = family == AlgorithmFamily.RSA && algorithm.keySizeBits().filter(bits -> bits < MIN_SAFE_RSA_BITS).isPresent();
        boolean brokenDigest = family == AlgorithmFamily.MD5 || family == AlgorithmFamily.SHA1;
        boolean weakDigestInSignature = brokenDigest && SIGNATURE_CONTEXTS.contains(usage.usageContext());
        boolean ecbBlockCipher = (family == AlgorithmFamily.AES || weakCipher) && algorithm.mode().filter("ECB"::equals).isPresent();
        boolean rsaV15Encryption = family == AlgorithmFamily.RSA && algorithm.padding().filter("PKCS1_V1_5"::equals).isPresent()
                && KEY_ESTABLISHMENT.contains(usage.usageContext());
        return weakCipher || weakRsaKey || weakDigestInSignature || ecbBlockCipher || rsaV15Encryption;
    }
}
