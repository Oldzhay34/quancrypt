package com.quancrypt.core.unit.domain;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.domain.policy.CryptoUsageSpecs;
import com.quancrypt.core.domain.policy.PriorityClassifier;
import com.quancrypt.core.domain.policy.PriorityVerdict;
import com.quancrypt.core.domain.policy.Specification;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.assertj.core.api.Assertions.assertThat;

class PriorityClassifierTest {

    private final PriorityClassifier classifier = new PriorityClassifier();

    @ParameterizedTest(name = "{0} {1} key={2} {3} -> {4}")
    @CsvSource(value = {
            "DES, ENCRYPTION, , CODE, P0",
            "TRIPLE_DES, SYMMETRIC_ENCRYPTION, , CODE, P0",
            "RSA, SIGNATURE, 1024, CERTIFICATE_FILE, P0",
            "RSA, TLS_KEY_EXCHANGE, 1024, CONFIG, P0",
            "MD5, SIGNATURE, , CODE, P0",
            "SHA1, SIGNATURE, , CODE, P0",
            "SHA1, TOKEN_SIGNATURE, , CODE, P0",
            "SHA1, CERTIFICATE, , CERTIFICATE_FILE, P0",
            "SHA1, HASH, , CODE, NOT_APPLICABLE",
            "MD5, HASH, , CODE, NOT_APPLICABLE",
            "RSA, TLS_KEY_EXCHANGE, 2048, CODE, P1",
            "RSA, TLS_KEY_EXCHANGE, , CONFIG, P1",
            "ECDH, TLS_KEY_EXCHANGE, , CODE, P1",
            "X25519, TLS_KEY_EXCHANGE, , CODE, P1",
            "RSA, ENCRYPTION, 2048, CODE, P1",
            "RSA, KEY_WRAP, 2048, CODE, P1",
            "ECDH, KEY_AGREEMENT, , CODE, P1",
            "DH, KEY_AGREEMENT, , CODE, P1",
            "ECDSA, SIGNATURE, , CODE, P2",
            "RSA, SIGNATURE, 2048, CODE, P2",
            "DSA, SIGNATURE, , CODE, P2",
            "EDDSA, SIGNATURE, , CODE, P2",
            "RSA, TOKEN_SIGNATURE, 2048, CODE, P3",
            "RSA, CERTIFICATE, 2048, CERTIFICATE_FILE, P3",
            "RSA, MTLS_CLIENT_AUTH, 2048, CONFIG, P3",
            "RSA, TLS_SERVER_AUTH, 2048, CONFIG, P3",
            "UNKNOWN, KEYSTORE, , KEYSTORE_FILE, P3",
            "RSA, UNKNOWN, , KEYSTORE_FILE, P3",
            "AES, ENCRYPTION, , CODE, NOT_APPLICABLE",
            "CHACHA20, ENCRYPTION, , CODE, NOT_APPLICABLE",
            "SHA2, HASH, , CODE, NOT_APPLICABLE",
            "SHA3, HASH, , CODE, NOT_APPLICABLE",
            "HMAC, HASH, , CODE, NOT_APPLICABLE",
            "ML_KEM, TLS_KEY_EXCHANGE, , CODE, NOT_APPLICABLE",
            "ML_DSA, SIGNATURE, , CODE, NOT_APPLICABLE",
            "SLH_DSA, SIGNATURE, , CODE, NOT_APPLICABLE",
            "HYBRID_X25519_MLKEM768, TLS_KEY_EXCHANGE, , CONFIG, NOT_APPLICABLE",
            "UNKNOWN, TLS_KEY_EXCHANGE, , CODE, UNDETERMINED",
            "RSA, UNKNOWN, 2048, CODE, UNDETERMINED",
            "RSA, HASH, 2048, CODE, UNDETERMINED",
            "ECDSA, SYMMETRIC_ENCRYPTION, , CODE, UNDETERMINED"
    }, ignoreLeadingAndTrailingWhitespace = true)
    void theTableAssignsTheDocumentedPriority(AlgorithmFamily algorithm, UsageContext usage, String keySize, LocationKind kind, String expected) {
        Optional<Integer> bits = keySize == null || keySize.isBlank() ? Optional.empty() : Optional.of(Integer.parseInt(keySize));
        PriorityVerdict verdict = classifier.classify(new CryptoUsage(algorithm, usage, bits, kind));
        assertThat(describe(verdict)).isEqualTo(expected);
    }

    private static String describe(PriorityVerdict verdict) {
        return switch (verdict) {
            case PriorityVerdict.Derived derived -> derived.priority().name();
            case PriorityVerdict.NotApplicable notApplicable -> "NOT_APPLICABLE";
            case PriorityVerdict.Undetermined undetermined -> "UNDETERMINED";
        };
    }

    @Test
    void anRsaKeyOf2048BitsIsNotWeak() {
        assertThat(CryptoUsageSpecs.WEAK_RSA_KEY.isSatisfiedBy(new CryptoUsage(AlgorithmFamily.RSA, UsageContext.SIGNATURE, Optional.of(2048), LocationKind.CODE))).isFalse();
        assertThat(CryptoUsageSpecs.WEAK_RSA_KEY.isSatisfiedBy(new CryptoUsage(AlgorithmFamily.RSA, UsageContext.SIGNATURE, Optional.of(2047), LocationKind.CODE))).isTrue();
    }

    @Test
    void specificationsCombine() {
        Specification<CryptoUsage> weakSignature = CryptoUsageSpecs.WEAK_CLASSIC.and(CryptoUsageSpecs.SIGNATURE_CONTEXT);
        CryptoUsage md5Signature = new CryptoUsage(AlgorithmFamily.MD5, UsageContext.SIGNATURE, Optional.empty(), LocationKind.CODE);
        CryptoUsage aesEncryption = new CryptoUsage(AlgorithmFamily.AES, UsageContext.ENCRYPTION, Optional.empty(), LocationKind.CODE);
        assertThat(weakSignature.isSatisfiedBy(md5Signature)).isTrue();
        assertThat(weakSignature.isSatisfiedBy(aesEncryption)).isFalse();
        assertThat(weakSignature.not().isSatisfiedBy(aesEncryption)).isTrue();
        assertThat(CryptoUsageSpecs.QUANTUM_VULNERABLE.or(CryptoUsageSpecs.NEEDS_NO_MIGRATION).isSatisfiedBy(aesEncryption)).isTrue();
        assertThat(Specification.<CryptoUsage>of(u -> false).isSatisfiedBy(md5Signature)).isFalse();
    }
}
