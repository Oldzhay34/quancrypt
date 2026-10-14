package com.quancrypt.analyzer.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.Evidence;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.Priority;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.domain.policy.PriorityClassifier;
import com.quancrypt.analyzer.domain.policy.PriorityVerdict;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** The crypto-domain priority table, rule by rule (D-186; the same cases core-service's classifier has). */
class PriorityClassifierTest {

    private final PriorityClassifier classifier = new PriorityClassifier();

    private static CryptoUsage usage(AlgorithmFamily family, UsageContext context, Integer keyBits, String mode, String padding,
            LocationKind kind) {
        return new CryptoUsage(new Evidence(RelativePath.of("A.java"), Optional.empty(), kind), "A#a",
                new CryptoAlgorithm(family, family.name(), Optional.ofNullable(mode), Optional.ofNullable(padding), Optional.empty(),
                        Optional.ofNullable(keyBits)),
                context, Priority.P3, Optional.empty(), 1.0, "test.detector");
    }

    private PriorityVerdict classify(AlgorithmFamily family, UsageContext context, Integer keyBits) {
        return classifier.classify(usage(family, context, keyBits, null, null, LocationKind.CODE));
    }

    @Test
    void weakClassicCryptoIsP0() {
        assertThat(classify(AlgorithmFamily.DES, UsageContext.SYMMETRIC_ENCRYPTION, null)).isEqualTo(new PriorityVerdict.Derived(Priority.P0));
        assertThat(classify(AlgorithmFamily.TRIPLE_DES, UsageContext.ENCRYPTION, null)).isEqualTo(new PriorityVerdict.Derived(Priority.P0));
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.SIGNATURE, 1024)).isEqualTo(new PriorityVerdict.Derived(Priority.P0));
        assertThat(classify(AlgorithmFamily.SHA1, UsageContext.SIGNATURE, null)).isEqualTo(new PriorityVerdict.Derived(Priority.P0));
        assertThat(classify(AlgorithmFamily.MD5, UsageContext.CERTIFICATE, null)).isEqualTo(new PriorityVerdict.Derived(Priority.P0));
    }

    @Test
    void ecbModeAndPkcs1EncryptionAreP0() {
        assertThat(classifier.classify(usage(AlgorithmFamily.AES, UsageContext.SYMMETRIC_ENCRYPTION, 128, "ECB", null, LocationKind.CODE)))
                .isEqualTo(new PriorityVerdict.Derived(Priority.P0));
        assertThat(classifier.classify(usage(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, 2048, "NONE", "PKCS1_V1_5", LocationKind.CODE)))
                .isEqualTo(new PriorityVerdict.Derived(Priority.P0));
        assertThat(classifier.classify(usage(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, 2048, "NONE", "OAEP", LocationKind.CODE)))
                .isEqualTo(new PriorityVerdict.Derived(Priority.P1));
        assertThat(classifier.classify(usage(AlgorithmFamily.RSA, UsageContext.SIGNATURE, 2048, null, "PKCS1_V1_5", LocationKind.CODE)))
                .isEqualTo(new PriorityVerdict.Derived(Priority.P2));
    }

    @Test
    void quantumVulnerableUsagesFollowTheTable() {
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE, 2048)).isEqualTo(new PriorityVerdict.Derived(Priority.P1));
        assertThat(classify(AlgorithmFamily.ECDH, UsageContext.KEY_AGREEMENT, null)).isEqualTo(new PriorityVerdict.Derived(Priority.P1));
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.KEY_WRAP, 2048)).isEqualTo(new PriorityVerdict.Derived(Priority.P1));
        assertThat(classify(AlgorithmFamily.ECDSA, UsageContext.SIGNATURE, null)).isEqualTo(new PriorityVerdict.Derived(Priority.P2));
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.TOKEN_SIGNATURE, 2048)).isEqualTo(new PriorityVerdict.Derived(Priority.P3));
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.CERTIFICATE, 2048)).isEqualTo(new PriorityVerdict.Derived(Priority.P3));
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.MTLS_CLIENT_AUTH, 2048)).isEqualTo(new PriorityVerdict.Derived(Priority.P3));
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.TLS_SERVER_AUTH, 2048)).isEqualTo(new PriorityVerdict.Derived(Priority.P3));
    }

    @Test
    void keystoreAssetsAreP3() {
        assertThat(classifier.classify(usage(AlgorithmFamily.UNKNOWN, UsageContext.KEYSTORE, null, null, null, LocationKind.KEYSTORE_FILE)))
                .isEqualTo(new PriorityVerdict.Derived(Priority.P3));
    }

    @Test
    void strongSymmetricHashAndResistantAlgorithmsNeedNoMigration() {
        assertThat(classify(AlgorithmFamily.AES, UsageContext.SYMMETRIC_ENCRYPTION, 256)).isEqualTo(new PriorityVerdict.NotApplicable());
        assertThat(classify(AlgorithmFamily.SHA2, UsageContext.HASH, null)).isEqualTo(new PriorityVerdict.NotApplicable());
        assertThat(classify(AlgorithmFamily.SHA1, UsageContext.HASH, null)).isEqualTo(new PriorityVerdict.NotApplicable());
        assertThat(classify(AlgorithmFamily.ML_KEM, UsageContext.KEY_AGREEMENT, null)).isEqualTo(new PriorityVerdict.NotApplicable());
        assertThat(classify(AlgorithmFamily.HYBRID_X25519_MLKEM768, UsageContext.TLS_KEY_EXCHANGE, null))
                .isEqualTo(new PriorityVerdict.NotApplicable());
    }

    @Test
    void unknownAlgorithmOrContextIsUndetermined() {
        assertThat(classify(AlgorithmFamily.UNKNOWN, UsageContext.TLS_SERVER_AUTH, null)).isEqualTo(new PriorityVerdict.Undetermined());
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.UNKNOWN, 2048)).isEqualTo(new PriorityVerdict.Undetermined());
        assertThat(classify(AlgorithmFamily.RSA, UsageContext.HASH, 2048)).isEqualTo(new PriorityVerdict.Undetermined());
    }
}
