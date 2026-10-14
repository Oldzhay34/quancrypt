package com.quancrypt.analyzer.unit.plugin;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AlgorithmFamily;
import com.quancrypt.analyzer.domain.model.UsageContext;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.Observation;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.code.JwtLibraryDetector;
import java.util.List;
import org.junit.jupiter.api.Test;

class JwtLibraryDetectorTest {

    private final JwtLibraryDetector detector = new JwtLibraryDetector(DetectorHarness.names());

    private DetectorHarness.Outcome run(String imports, String body) {
        return DetectorHarness.run(detector, "src/main/java/Tokens.java", imports + """

                class Tokens {
                    void run() throws Exception {
                        %s
                    }
                }
                """.replace("%s", body));
    }

    @Test
    void nimbusAlgorithmConstantsAreTokenSignatures() {
        Observation found = run("import com.nimbusds.jose.JWSAlgorithm;", "Object a = JWSAlgorithm.RS256;").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.algorithm().hash()).contains("SHA-256");
        assertThat(found.usage()).isEqualTo(UsageContext.TOKEN_SIGNATURE);
        assertThat(found.library()).contains("nimbus-jose-jwt");
        assertThat(found.detectorId()).isEqualTo("jwt.library");
    }

    @Test
    void jjwtAndSpringConstantsAreFoundToo() {
        assertThat(run("import io.jsonwebtoken.SignatureAlgorithm;", "Object a = SignatureAlgorithm.ES256;").only().algorithm().family())
                .isEqualTo(AlgorithmFamily.ECDSA);
        assertThat(run("import io.jsonwebtoken.Jwts;", "Object a = Jwts.SIG.PS384;").only().algorithm().padding()).contains("PSS");
        assertThat(run("import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;", "Object a = SignatureAlgorithm.RS512;").only()
                .library()).contains("spring-security-oauth2-jose");
    }

    @Test
    void auth0AlgorithmFactoriesAreFound() {
        Observation found = run("import com.auth0.jwt.algorithms.Algorithm;", "Algorithm.RSA256(null, null);").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.library()).contains("java-jwt");
    }

    @Test
    void hmacTokensAreSeenAsHmac() {
        assertThat(run("import com.nimbusds.jose.JWSAlgorithm;", "Object a = JWSAlgorithm.HS256;").only().algorithm().family())
                .isEqualTo(AlgorithmFamily.HMAC);
    }

    @Test
    void nimbusSignersAndKeysAreRsaTokenSignatures() {
        List<Observation> found = run("import com.nimbusds.jose.crypto.RSASSASigner;\nimport com.nimbusds.jose.jwk.RSAKey;",
                "new RSASSASigner((RSAKey) null);").observations();

        assertThat(found).extracting(o -> o.algorithm().rawName()).containsExactlyInAnyOrder("RSASSASigner", "RSAKey");
        assertThat(found).extracting(Observation::confidence).containsOnly(0.7);
    }

    @Test
    void springDecoderBuildersDefaultToRs256UnlessTheAlgorithmIsSet() {
        String imports = "import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;\n"
                + "import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;";

        Observation defaulted = run(imports, "NimbusJwtDecoder.withJwkSetUri(\"https://idp/jwks\").build();").only();
        List<Observation> explicit = run(imports,
                "NimbusJwtDecoder.withPublicKey(null).signatureAlgorithm(SignatureAlgorithm.ES256).build();").observations();

        assertThat(defaulted.algorithm().rawName()).isEqualTo("RS256");
        assertThat(defaulted.confidence()).isEqualTo(0.6);
        assertThat(explicit).hasSize(1);
        assertThat(explicit.get(0).algorithm().family()).isEqualTo(AlgorithmFamily.ECDSA);
    }

    @Test
    void anAlgorithmNameWrittenAsAStringLiteralIsFoundEvenWithoutAJwtImport() {
        Observation found = run("", "String alg = \"RS256\";").only();

        assertThat(found.algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.confidence()).isEqualTo(0.6);
        assertThat(found.library()).isEmpty();
        assertThat(run("", "String alg = \"HS256\";").observations()).isEmpty();
    }

    @Test
    void aSameNamedConstantOfAnotherLibraryIsNotMistaken() {
        assertThat(run("", "Object a = SignatureAlgorithm.RS256;").observations()).isEmpty();
    }

    @Test
    void aSpringEncoderIsFoundThroughTheAlgorithmOfItsHeader() {
        List<Observation> found = run("import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;\n"
                + "import org.springframework.security.oauth2.jwt.JwsHeader;\n"
                + "import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;",
                "new NimbusJwtEncoder(null); JwsHeader.with(SignatureAlgorithm.PS256).build();").observations();

        assertThat(found).hasSize(1);
        assertThat(found.get(0).algorithm().family()).isEqualTo(AlgorithmFamily.RSA);
        assertThat(found.get(0).algorithm().padding()).contains("PSS");
        assertThat(found.get(0).library()).contains("spring-security-oauth2-jose");
    }
}
