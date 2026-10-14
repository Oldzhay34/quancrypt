package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.NameSanitizer;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemFacts;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.pem.PemRole;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class PemReaderTest {

    private final PemReader reader = new PemReader(DetectorHarness.names());
    private final RelativePath file = RelativePath.of("certs/x.pem");

    private static List<String> lines(String text) {
        return text.lines().toList();
    }

    @Test
    void anyLabelThatNamesAPrivateKeyIsOnlyRecognisedFromItsHeader() {
        PemFacts pgp = reader.read(file, lines("-----BEGIN PGP PRIVATE KEY BLOCK-----\nAAAA\n-----END PGP PRIVATE KEY BLOCK-----")).orElseThrow();

        assertThat(pgp.role()).isEqualTo(PemRole.PRIVATE_KEY);
        assertThat(pgp.family()).isEmpty();
    }

    @Test
    void aBlockWithoutAnEndLineStopsAtTheNextBeginLine() {
        String truncatedPublicKey = TestPems.RSA_2048_PUBLIC_KEY.replace("-----END PUBLIC KEY-----", "").stripTrailing();

        PemFacts facts = reader.read(file, lines(truncatedPublicKey + "\n" + TestPems.PRIVATE_KEY_PLACEHOLDER)).orElseThrow();

        assertThat(facts.family()).contains(AlgorithmFamily.RSA);
        assertThat(facts.keySizeBits()).contains(2048);
    }

    @Test
    void aCompanionPathTooLongToBeAPathIsSkipped() {
        RelativePath privateKey = RelativePath.of("d/".repeat(509) + "k.key");
        PemFacts key = new PemFacts(privateKey, PemRole.PRIVATE_KEY, "PRIVATE KEY", Optional.empty(), Optional.empty(), Optional.empty());

        PemIndex index = new PemIndex(List.of(key));

        assertThat(index.counterpart(privateKey)).isEmpty();
    }

    @Test
    void aSanitizedNameNeverExceedsTheContractLengthEvenWithASupplementaryCharacter() {
        String cleaned = NameSanitizer.clean("a".repeat(255) + "\uD83D\uDE00");

        assertThat(cleaned.length()).isLessThanOrEqualTo(256);
    }
}
