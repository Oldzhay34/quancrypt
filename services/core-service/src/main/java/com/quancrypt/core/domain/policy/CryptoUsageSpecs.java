package com.quancrypt.core.domain.policy;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.QuantumStatus;
import com.quancrypt.core.domain.model.UsageContext;
import java.util.EnumSet;
import java.util.Set;

/** The building blocks of the crypto-domain priority table as combinable specifications (D-149, D-151). */
public final class CryptoUsageSpecs {

    public static final int MIN_SAFE_RSA_BITS = 2048;

    private static final Set<UsageContext> SIGNATURE_CONTEXTS = EnumSet.of(
            UsageContext.SIGNATURE, UsageContext.TOKEN_SIGNATURE, UsageContext.CERTIFICATE,
            UsageContext.TLS_SERVER_AUTH, UsageContext.MTLS_CLIENT_AUTH);
    private static final Set<UsageContext> KEY_ESTABLISHMENT = EnumSet.of(
            UsageContext.ENCRYPTION, UsageContext.KEY_WRAP, UsageContext.KEY_AGREEMENT);
    private static final Set<UsageContext> IDENTITY_AND_CERTIFICATES = EnumSet.of(
            UsageContext.TLS_SERVER_AUTH, UsageContext.MTLS_CLIENT_AUTH, UsageContext.CERTIFICATE);

    public static final Specification<CryptoUsage> QUANTUM_VULNERABLE = u -> u.algorithm().isQuantumVulnerable();
    public static final Specification<CryptoUsage> NEEDS_NO_MIGRATION = u -> u.algorithm().quantumStatus()
            .filter(s -> s == QuantumStatus.RESISTANT || s == QuantumStatus.SYMMETRIC_OR_HASH).isPresent();
    public static final Specification<CryptoUsage> WEAK_CIPHER =
            u -> u.algorithm() == AlgorithmFamily.DES || u.algorithm() == AlgorithmFamily.TRIPLE_DES;
    public static final Specification<CryptoUsage> WEAK_RSA_KEY =
            u -> u.algorithm() == AlgorithmFamily.RSA && u.keySizeBits().filter(bits -> bits < MIN_SAFE_RSA_BITS).isPresent();
    public static final Specification<CryptoUsage> SIGNATURE_CONTEXT = u -> SIGNATURE_CONTEXTS.contains(u.usage());
    public static final Specification<CryptoUsage> BROKEN_DIGEST =
            u -> u.algorithm() == AlgorithmFamily.MD5 || u.algorithm() == AlgorithmFamily.SHA1;
    public static final Specification<CryptoUsage> WEAK_DIGEST_IN_SIGNATURE = BROKEN_DIGEST.and(SIGNATURE_CONTEXT);
    public static final Specification<CryptoUsage> WEAK_CLASSIC = WEAK_CIPHER.or(WEAK_RSA_KEY).or(WEAK_DIGEST_IN_SIGNATURE);
    public static final Specification<CryptoUsage> KEYSTORE_ASSET =
            u -> u.usage() == UsageContext.KEYSTORE || u.locationKind() == LocationKind.KEYSTORE_FILE;
    public static final Specification<CryptoUsage> UNDETERMINED =
            u -> u.algorithm() == AlgorithmFamily.UNKNOWN || u.usage() == UsageContext.UNKNOWN;
    public static final Specification<CryptoUsage> TLS_KEY_EXCHANGE = u -> u.usage() == UsageContext.TLS_KEY_EXCHANGE;
    public static final Specification<CryptoUsage> KEY_ESTABLISHMENT_USAGE = u -> KEY_ESTABLISHMENT.contains(u.usage());
    public static final Specification<CryptoUsage> SIGNATURE_USAGE = u -> u.usage() == UsageContext.SIGNATURE;
    public static final Specification<CryptoUsage> TOKEN_SIGNATURE_USAGE = u -> u.usage() == UsageContext.TOKEN_SIGNATURE;
    public static final Specification<CryptoUsage> IDENTITY_OR_CERTIFICATE_USAGE = u -> IDENTITY_AND_CERTIFICATES.contains(u.usage());

    private CryptoUsageSpecs() {
    }
}
