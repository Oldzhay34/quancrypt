package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.ProjectIndex;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.TlsIdentity;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ProjectIndexTest {

    private static final String BUNDLES = """
            server:
              ssl:
                bundle: web
            spring:
              ssl:
                bundle:
                  pem:
                    web:
                      keystore:
                        certificate: "file:${CERTS:/certs}/web.crt.pem"
                    broken:
                      keystore:
                        certificate: "file:/certs/missing.crt.pem"
                    trusting:
                      truststore:
                        certificate: "file:/certs/ca.crt.pem"
            """;

    private ProjectIndex index(String... more) {
        String[] files = new String[more.length + 2];
        files[0] = "src/main/resources/application.yml";
        files[1] = BUNDLES;
        System.arraycopy(more, 0, files, 2, more.length);
        return DetectorHarness.index(files);
    }

    @Test
    void aBundlesIdentityIsTheKeyOfItsOwnCertificateFile() {
        ProjectIndex index = index("certs/web.crt.pem", TestPems.EC_P256_CERTIFICATE, "certs/ca.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        TlsIdentity identity = index.identityOf("web");
        assertThat(identity.family()).contains(AlgorithmFamily.ECDSA);
        assertThat(identity.keySizeBits()).contains(256);
        assertThat(identity.certain()).isTrue();
        assertThat(index.bundles().isServerBundle("web")).isTrue();
        assertThat(index.bundles().isServerBundle("trusting")).isFalse();
    }

    @Test
    void aTruststoreOnlyBundleUsesTheCertificateItTrusts() {
        ProjectIndex index = index("certs/web.crt.pem", TestPems.EC_P256_CERTIFICATE, "certs/ca.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        assertThat(index.identityOf("trusting").family()).contains(AlgorithmFamily.RSA);
    }

    @Test
    void whenTheFileIsMissingOrTheBundleUnknownTheProjectDefaultIsUsedAsAGuess() {
        ProjectIndex agreeing = index("certs/a.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/b.crt.pem", TestPems.RSA_2048_CERTIFICATE);
        ProjectIndex disagreeing = index("certs/a.crt.pem", TestPems.RSA_2048_CERTIFICATE, "certs/b.crt.pem", TestPems.EC_P256_CERTIFICATE);

        assertThat(agreeing.identityOf("broken")).isEqualTo(new TlsIdentity(Optional.of(AlgorithmFamily.RSA), Optional.of(2048), false));
        assertThat(agreeing.identityOf("nonexistent").family()).contains(AlgorithmFamily.RSA);
        assertThat(disagreeing.identityOf("broken")).isEqualTo(TlsIdentity.UNKNOWN);
        assertThat(index().defaultIdentity()).isEqualTo(TlsIdentity.UNKNOWN);
    }

    @Test
    void certificateFilesInConfigurationAreFoundByTheirBaseName() {
        ProjectIndex index = index("certs/web.crt.pem", TestPems.EC_P256_CERTIFICATE);

        assertThat(index.identityOfFile("file:${somewhere}/deep/web.crt.pem").family()).contains(AlgorithmFamily.ECDSA);
        assertThat(ProjectIndex.basename("classpath:certs/x.pem")).isEqualTo("x.pem");
        assertThat(ProjectIndex.basename("C:\\keys\\x.pem")).isEqualTo("x.pem");
    }

    @Test
    void twoFilesWithTheSameBaseNameAreNotGuessedBetween() {
        ProjectIndex index = index("a/web.crt.pem", TestPems.EC_P256_CERTIFICATE, "b/web.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        assertThat(index.pem().byBasename("web.crt.pem")).isEmpty();
    }

    @Test
    void generatedOutputIsNotIndexed() {
        ProjectIndex index = DetectorHarness.index("pom.xml", "<project/>", "build/x/web.crt.pem", TestPems.EC_P256_CERTIFICATE,
                "target/y.crt.pem", TestPems.EC_P256_CERTIFICATE, "certs/real.crt.pem", TestPems.RSA_2048_CERTIFICATE);

        assertThat(index.pem().all()).extracting(f -> f.file().value()).containsExactly("certs/real.crt.pem");
    }
}

