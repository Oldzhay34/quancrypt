package com.quancrypt.analyzer.infrastructure.cbom;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.Optional;
import java.util.Set;
import org.cyclonedx.model.component.crypto.enums.Mode;
import org.cyclonedx.model.component.crypto.enums.Padding;
import org.cyclonedx.model.component.crypto.enums.Primitive;

/**
 * Maps the codes of crypto-domain and the canonical dictionary onto the closed lists of the CycloneDX 1.6 schema
 * (primitive, mode, padding). The primitives follow the examples of the schema's own descriptions (RSA is "pke", ECDSA a
 * signature, ECDH key agreement, ML-KEM a kem, AES-GCM authenticated encryption, HMAC a mac); RSA is a signature or a pke
 * only when the usage context says which. What the schema has no
 * value for, or what is not certain, maps to nothing (mode, padding) or to {@code unknown} (primitive, which the schema
 * requires).
 */
final class AlgorithmMapping {

    private static final Set<UsageContext> SIGNING = Set.of(UsageContext.SIGNATURE, UsageContext.TOKEN_SIGNATURE);
    private static final Set<UsageContext> ENCRYPTING = Set.of(UsageContext.ENCRYPTION, UsageContext.KEY_WRAP);

    private AlgorithmMapping() {
    }

    static Primitive primitive(AlgorithmFamily family, UsageContext usage, Optional<String> mode) {
        return switch (family) {
            // Only where the use says what RSA does; in a certificate or a TLS connection it could be either, so it is unknown.
            case RSA -> SIGNING.contains(usage) ? Primitive.SIGNATURE : ENCRYPTING.contains(usage) ? Primitive.PKE : Primitive.UNKNOWN;
            case ECDSA, EDDSA, DSA, ML_DSA, SLH_DSA -> Primitive.SIGNATURE;
            case ECDH, DH, X25519 -> Primitive.KEY_AGREE;
            case ML_KEM -> Primitive.KEM;
            case AES, DES, TRIPLE_DES -> authenticated(mode) ? Primitive.AE : Primitive.BLOCK_CIPHER;
            case CHACHA20 -> Primitive.STREAM_CIPHER;
            case SHA1, SHA2, SHA3, MD5 -> Primitive.HASH;
            case HMAC -> Primitive.MAC;
            case HYBRID_X25519_MLKEM768, UNKNOWN -> Primitive.UNKNOWN;
        };
    }

    private static boolean authenticated(Optional<String> mode) {
        return mode.filter(m -> m.equals("GCM") || m.equals("CCM")).isPresent();
    }

    static Optional<Mode> mode(Optional<String> mode) {
        return mode.flatMap(m -> switch (m) {
            case "CBC" -> Optional.of(Mode.CBC);
            case "ECB" -> Optional.of(Mode.ECB);
            case "CCM" -> Optional.of(Mode.CCM);
            case "GCM" -> Optional.of(Mode.GCM);
            case "CFB" -> Optional.of(Mode.CFB);
            case "OFB" -> Optional.of(Mode.OFB);
            case "CTR" -> Optional.of(Mode.CTR);
            case "CFB8", "CTS", "PCBC" -> Optional.of(Mode.OTHER);
            default -> Optional.empty();
        });
    }

    static Optional<Padding> padding(Optional<String> padding) {
        return padding.flatMap(p -> switch (p) {
            case "PKCS5" -> Optional.of(Padding.PKCS5);
            case "PKCS7" -> Optional.of(Padding.PKCS7);
            case "PKCS1_V1_5" -> Optional.of(Padding.PKCS1V15);
            case "OAEP" -> Optional.of(Padding.OAEP);
            case "ISO10126", "PSS" -> Optional.of(Padding.OTHER);
            default -> Optional.empty();
        });
    }

    /** Level 0 ("none of the categories are met" in the schema) only for the families crypto-domain marks vulnerable (D-197). */
    static Optional<Integer> nistQuantumSecurityLevel(AlgorithmFamily family) {
        return family.isQuantumVulnerable() ? Optional.of(0) : Optional.empty();
    }
}
