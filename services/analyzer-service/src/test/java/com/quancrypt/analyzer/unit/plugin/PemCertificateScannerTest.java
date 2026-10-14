package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.file.PemCertificateScanner;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class PemCertificateScannerTest {

    private final PemCertificateScanner scanner = new PemCertificateScanner(DetectorHarness.names());

    private Map<String, List<Observation>> byFile(DetectorHarness.Outcome outcome) {
        return outcome.observations().stream().collect(Collectors.groupingBy(o -> o.evidence().file().value()));
    }

    @Test
    void anRsaCertificateGivesKeyAlgorithmSizeAndSignature() {
        Observation found = DetectorHarness.run(scanner, "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE).only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.algorithm().keySizeBits()).contains(2048);
        assertThat(found.algorithm().rawName()).isEqualTo("X.509 SHA256withRSA");
        assertThat(found.usage()).isEqualTo(UsageContext.CERTIFICATE);
        assertThat(found.confidence()).isEqualTo(0.95);
        assertThat(found.evidence().locationKind()).isEqualTo(LocationKind.CERTIFICATE_FILE);
        assertThat(found.evidence().lines()).isEmpty();
        assertThat(found.symbol()).isEqualTo("server.crt.pem");
        assertThat(found.detectorId()).isEqualTo("pem.certificate");
    }

    @Test
    void anEllipticCurveCertificateIsEcdsa() {
        Observation found = DetectorHarness.run(scanner, "certs/ec.crt.pem", TestPems.EC_P256_CERTIFICATE).only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
        assertThat(found.algorithm().keySizeBits()).contains(256);
    }

    @Test
    void aWeakCertificateIsAlsoReportedForItsBrokenHash() {
        List<Observation> found = DetectorHarness.run(scanner, "certs/weak.crt.pem", TestPems.RSA_1024_SHA1_CERTIFICATE).observations();

        assertThat(found).extracting(o -> o.algorithm().family()).containsExactly(AlgorithmFamily.RSA, AlgorithmFamily.SHA1);
        assertThat(found.get(0).algorithm().keySizeBits()).contains(1024);
        assertThat(found).extracting(Observation::usage).containsOnly(UsageContext.CERTIFICATE);
    }

    @Test
    void aPublicKeyWaitsForTheCodeThatLoadsIt() {
        Observation found = DetectorHarness.run(scanner, "certs/app.pub.pem", TestPems.RSA_2048_PUBLIC_KEY).only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.algorithm().keySizeBits()).contains(2048);
        assertThat(found.usageFromLoader()).isTrue();
        assertThat(found.usage()).isEqualTo(UsageContext.UNKNOWN);
    }

    @Test
    void aPrivateKeyNextToItsCertificateBelongsToTheCertificate() {
        Map<String, List<Observation>> found = byFile(DetectorHarness.run(scanner, "certs/server.crt.pem", TestPems.RSA_2048_CERTIFICATE,
                "certs/server.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER));

        Observation key = found.get("certs/server.key.pem").get(0);
        assertThat(key.usage()).isEqualTo(UsageContext.CERTIFICATE);
        assertThat(key.usageFromLoader()).isFalse();
        assertThat(key.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(key.algorithm().keySizeBits()).contains(2048);
        assertThat(key.algorithm().rawName()).isEqualTo("PRIVATE KEY");
    }

    @Test
    void aPrivateKeyNextToAPublicKeyTakesItsKeyAndWaitsForTheLoader() {
        Map<String, List<Observation>> found = byFile(DetectorHarness.run(scanner, "certs/app.pub.pem", TestPems.RSA_2048_PUBLIC_KEY,
                "certs/app.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER));

        Observation key = found.get("certs/app.key.pem").get(0);
        assertThat(key.usageFromLoader()).isTrue();
        assertThat(key.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(key.algorithm().keySizeBits()).contains(2048);
    }

    @Test
    void aLonePrivateKeyIsKnownOnlyByItsHeader() {
        Observation typed = DetectorHarness.run(scanner, "keys/a.key.pem", TestPems.RSA_PRIVATE_KEY_PLACEHOLDER).only();
        Observation untyped = DetectorHarness.run(scanner, "keys/b.key.pem", TestPems.PRIVATE_KEY_PLACEHOLDER).only();

        assertThat(typed.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(typed.algorithm().keySizeBits()).isEmpty();
        assertThat(untyped.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
    }

    @Test
    void filesThatAreNotPemOrAreOtherPemKindsAreIgnored() {
        assertThat(DetectorHarness.run(scanner, "certs/readme.pem", "no pem here").observations()).isEmpty();
        assertThat(DetectorHarness.run(scanner, "certs/request.csr.pem", "-----BEGIN CERTIFICATE REQUEST-----\nAAAA\n-----END CERTIFICATE REQUEST-----\n")
                .observations()).isEmpty();
    }

    @Test
    void aBrokenCertificateIsStillReportedAsAnUnknownKey() {
        Observation found = DetectorHarness.run(scanner, "certs/broken.crt.pem",
                "-----BEGIN CERTIFICATE-----\nAAAAAAAA\n-----END CERTIFICATE-----\n").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.UNKNOWN);
        assertThat(found.confidence()).isEqualTo(0.4);
    }
}

