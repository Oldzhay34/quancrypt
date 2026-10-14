package com.quancrypt.analyzer.infrastructure.cbom;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.cyclonedx.model.component.crypto.enums.Mode;
import org.cyclonedx.model.component.crypto.enums.Padding;
import org.cyclonedx.model.component.crypto.enums.Primitive;

/** The mapping of crypto-domain and dictionary codes onto the closed lists of the CycloneDX 1.6 schema (D-204). */
class AlgorithmMappingTest {

    @ParameterizedTest
    @EnumSource(AlgorithmFamily.class)
    void theQuantumLevelIsZeroExactlyForTheFamiliesCryptoDomainCallsVulnerable(AlgorithmFamily family) {
        assertThat(AlgorithmMapping.nistQuantumSecurityLevel(family)).isEqualTo(family.isQuantumVulnerable() ? Optional.of(0) : Optional.empty());
    }

    @ParameterizedTest
    @EnumSource(AlgorithmFamily.class)
    void everyFamilyHasAPrimitiveInEveryContext(AlgorithmFamily family) {
        for (UsageContext usage : UsageContext.values()) {
            assertThat(AlgorithmMapping.primitive(family, usage, Optional.empty())).isNotNull();
        }
    }

    @Test
    void rsaIsASignatureOrAPkeOnlyWhereTheUsageSaysWhichAndUnknownOtherwise() {
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.RSA, UsageContext.SIGNATURE, Optional.empty())).isEqualTo(Primitive.SIGNATURE);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.RSA, UsageContext.TOKEN_SIGNATURE, Optional.empty())).isEqualTo(Primitive.SIGNATURE);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.RSA, UsageContext.ENCRYPTION, Optional.empty())).isEqualTo(Primitive.PKE);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.RSA, UsageContext.KEY_WRAP, Optional.empty())).isEqualTo(Primitive.PKE);
        for (UsageContext usage : new UsageContext[] {UsageContext.CERTIFICATE, UsageContext.TLS_KEY_EXCHANGE, UsageContext.TLS_SERVER_AUTH,
            UsageContext.MTLS_CLIENT_AUTH, UsageContext.UNKNOWN}) {
            assertThat(AlgorithmMapping.primitive(AlgorithmFamily.RSA, usage, Optional.empty())).as(usage.name()).isEqualTo(Primitive.UNKNOWN);
        }
    }

    @Test
    void otherFamiliesFollowTheExamplesOfTheSchema() {
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.ECDSA, UsageContext.SIGNATURE, Optional.empty())).isEqualTo(Primitive.SIGNATURE);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.ECDH, UsageContext.KEY_AGREEMENT, Optional.empty())).isEqualTo(Primitive.KEY_AGREE);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.ML_KEM, UsageContext.ENCRYPTION, Optional.empty())).isEqualTo(Primitive.KEM);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.HMAC, UsageContext.HASH, Optional.empty())).isEqualTo(Primitive.MAC);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.CHACHA20, UsageContext.SYMMETRIC_ENCRYPTION, Optional.empty())).isEqualTo(Primitive.STREAM_CIPHER);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.SHA2, UsageContext.HASH, Optional.empty())).isEqualTo(Primitive.HASH);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.AES, UsageContext.SYMMETRIC_ENCRYPTION, Optional.of("GCM"))).isEqualTo(Primitive.AE);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.AES, UsageContext.SYMMETRIC_ENCRYPTION, Optional.of("CBC"))).isEqualTo(Primitive.BLOCK_CIPHER);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.DES, UsageContext.SYMMETRIC_ENCRYPTION, Optional.empty())).isEqualTo(Primitive.BLOCK_CIPHER);
        assertThat(AlgorithmMapping.primitive(AlgorithmFamily.UNKNOWN, UsageContext.UNKNOWN, Optional.empty())).isEqualTo(Primitive.UNKNOWN);
    }

    @Test
    void modesAndPaddingsMapToTheSchemaListsAndWhatHasNoValueMapsToNothing() {
        assertThat(AlgorithmMapping.mode(Optional.of("CBC"))).contains(Mode.CBC);
        assertThat(AlgorithmMapping.mode(Optional.of("ECB"))).contains(Mode.ECB);
        assertThat(AlgorithmMapping.mode(Optional.of("GCM"))).contains(Mode.GCM);
        assertThat(AlgorithmMapping.mode(Optional.of("CFB8"))).contains(Mode.OTHER);
        assertThat(AlgorithmMapping.mode(Optional.of("CTS"))).contains(Mode.OTHER);
        assertThat(AlgorithmMapping.mode(Optional.of("PCBC"))).contains(Mode.OTHER);
        assertThat(AlgorithmMapping.mode(Optional.of("NONE"))).isEmpty();
        assertThat(AlgorithmMapping.mode(Optional.of("TLSv1.2"))).isEmpty();
        assertThat(AlgorithmMapping.mode(Optional.empty())).isEmpty();
        assertThat(AlgorithmMapping.padding(Optional.of("PKCS5"))).contains(Padding.PKCS5);
        assertThat(AlgorithmMapping.padding(Optional.of("PKCS7"))).contains(Padding.PKCS7);
        assertThat(AlgorithmMapping.padding(Optional.of("PKCS1_V1_5"))).contains(Padding.PKCS1V15);
        assertThat(AlgorithmMapping.padding(Optional.of("OAEP"))).contains(Padding.OAEP);
        assertThat(AlgorithmMapping.padding(Optional.of("ISO10126"))).contains(Padding.OTHER);
        assertThat(AlgorithmMapping.padding(Optional.of("PSS"))).contains(Padding.OTHER);
        assertThat(AlgorithmMapping.padding(Optional.of("NONE"))).isEmpty();
        assertThat(AlgorithmMapping.padding(Optional.empty())).isEmpty();
    }
}
