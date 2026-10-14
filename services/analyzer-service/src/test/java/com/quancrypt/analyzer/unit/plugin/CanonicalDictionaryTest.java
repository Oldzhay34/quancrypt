package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.CanonicalDictionary;
import com.quancrypt.analyzer.domain.model.CanonicalKind;
import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.domain.model.CryptoAlgorithm;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** The canonical dictionary: one source file, loaded and queried (P3.2, section 4). */
class CanonicalDictionaryTest {

    private static final String HEADER = "kind,raw,algorithm_family,mode,padding,hash,usage_context,key_size_bits\n";

    private final CanonicalNames names = DetectorHarness.names();

    @Test
    void theBuildCopiesTheContractsFileUnchangedIntoTheResources() throws IOException {
        Path source = Path.of(System.getProperty("quancrypt.contracts.dir")).resolve("canonical_dictionary.csv");
        try (var in = CanonicalDictionaryLoader.class.getResourceAsStream(CanonicalDictionaryLoader.RESOURCE)) {
            assertThat(in).isNotNull();
            assertThat(in.readAllBytes()).isEqualTo(Files.readAllBytes(source));
        }
    }

    @Test
    void theDocumentsExamplesResolveToTheirCodes() {
        CryptoAlgorithm rsa = names.transformation("RSA/ECB/PKCS1Padding").orElseThrow();
        assertThat(rsa.family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(rsa.mode()).contains("NONE");
        assertThat(rsa.padding()).contains("PKCS1_V1_5");

        CryptoAlgorithm signature = names.algorithm(CanonicalKind.SIGNATURE, "SHA256withRSA").orElseThrow();
        assertThat(signature.family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(signature.hash()).contains("SHA-256");
        assertThat(names.entry(CanonicalKind.SIGNATURE, "SHA256withRSA").orElseThrow().usage()).contains(UsageContext.SIGNATURE);

        CryptoAlgorithm token = names.algorithm(CanonicalKind.JWT_ALG, "RS256").orElseThrow();
        assertThat(token.family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(names.entry(CanonicalKind.JWT_ALG, "RS256").orElseThrow().usage()).contains(UsageContext.TOKEN_SIGNATURE);

        assertThat(names.algorithm(CanonicalKind.OID, "1.2.840.113549.1.1.1").orElseThrow().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(names.keySize("2K")).contains(2048);
    }

    @Test
    void transformationsAreSplitIntoFamilyModeAndPadding() {
        CryptoAlgorithm gcm = names.transformation("AES/GCM/NoPadding").orElseThrow();
        assertThat(gcm.family()).isEqualTo(AlgorithmFamily.AES);
        assertThat(gcm.mode()).contains("GCM");
        assertThat(gcm.padding()).contains("NONE");

        CryptoAlgorithm oaep = names.transformation("RSA/ECB/OAEPWithSHA-256AndMGF1Padding").orElseThrow();
        assertThat(oaep.mode()).contains("NONE");
        assertThat(oaep.padding()).contains("OAEP");
        assertThat(oaep.hash()).contains("SHA-256");

        CryptoAlgorithm bareAes = names.transformation("AES").orElseThrow();
        assertThat(bareAes.mode()).contains("ECB");
        assertThat(names.transformation("DESede/CBC/PKCS5Padding").orElseThrow().family()).isEqualTo(AlgorithmFamily.TRIPLE_DES);
    }

    @Test
    void spellingDifferencesOfTheSameNameAreIgnored() {
        assertThat(names.algorithm(CanonicalKind.HASH, "sha_256")).isPresent();
        assertThat(names.algorithm(CanonicalKind.HASH, "SHA256")).isPresent();
        assertThat(names.algorithm(CanonicalKind.HASH, "sha-1").orElseThrow().family()).isEqualTo(AlgorithmFamily.SHA1);
        assertThat(names.algorithm(CanonicalKind.HASH, "SHA").orElseThrow().family()).isEqualTo(AlgorithmFamily.SHA1);
    }

    @Test
    void unknownNamesResolveToNothing() {
        assertThat(names.transformation("Blowfish/CBC/PKCS5Padding")).isEmpty();
        assertThat(names.transformation("AES/XYZ/NoPadding")).isEmpty();
        assertThat(names.algorithm(CanonicalKind.SIGNATURE, "SHA512withMadeUp")).isEmpty();
        assertThat(names.keySize("big")).isEmpty();
    }

    @Test
    void aRowWithNoFamilyOnlyLendsItsOtherCodes() {
        assertThat(names.entry(CanonicalKind.MODE, "CBC").orElseThrow().family()).isEmpty();
        assertThat(names.entry(CanonicalKind.MODE, "CBC").orElseThrow().mode()).contains("CBC");
    }

    @Test
    void aMalformedFileFailsLoadingInsteadOfBeingHalfRead() {
        CanonicalDictionaryLoader loader = new CanonicalDictionaryLoader();
        assertThatThrownBy(() -> loader.load(stream("kind,raw\nalgorithm,AES\n"))).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> loader.load(stream(HEADER + "algorithm,AES,AES\n"))).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> loader.load(stream(HEADER + "algorithm,AES,NOT_A_FAMILY,,,,,\n"))).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> loader.load(stream(HEADER + "nonsense,AES,AES,,,,,\n"))).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> loader.load(stream(HEADER + "algorithm,AES,AES,,,,,x\n"))).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void twoRowsForTheSameSpellingAreRefused() throws IOException {
        assertThatThrownBy(() -> new CanonicalDictionaryLoader().load(stream(HEADER + "algorithm,AES,AES,,,,,\nalgorithm,aes,AES,,,,,\n")))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void theShippedDictionaryIsLoadedWithManyRows() throws IOException {
        CanonicalDictionary dictionary = new CanonicalDictionaryLoader().loadFromClasspath();

        assertThat(dictionary.size()).isGreaterThan(100);
        assertThat(dictionary.lookup(CanonicalKind.ALGORITHM, null)).isEqualTo(Optional.empty());
    }

    private static ByteArrayInputStream stream(String text) {
        return new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8));
    }
}
