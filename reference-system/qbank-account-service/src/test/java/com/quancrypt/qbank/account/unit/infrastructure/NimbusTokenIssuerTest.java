package com.quancrypt.qbank.account.unit.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.quancrypt.qbank.account.infrastructure.security.JwtKeyMaterial;
import com.quancrypt.qbank.account.infrastructure.security.NimbusTokenIssuer;
import com.quancrypt.qbank.account.support.TokenFactory;
import java.text.ParseException;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class NimbusTokenIssuerTest {

    private final JwtKeyMaterial keys = TokenFactory.realKeys();
    private final NimbusTokenIssuer issuer = new NimbusTokenIssuer(keys);

    @Test
    void issuesAnRs256TokenWithKeyIdAndExactlyTheClaimsSubIatExp() throws Exception {
        Instant issuedAt = Instant.parse("2026-10-07T10:00:00Z");

        String token = issuer.issue("demo1", issuedAt, Duration.ofMinutes(15));

        SignedJWT jwt = SignedJWT.parse(token);
        assertThat(jwt.getHeader().getAlgorithm()).isEqualTo(JWSAlgorithm.RS256);
        assertThat(jwt.getHeader().getKeyID()).isEqualTo(keys.keyId());
        assertThat(jwt.verify(new RSASSAVerifier(keys.publicKey()))).isTrue();
        JWTClaimsSet claims = jwt.getJWTClaimsSet();
        assertThat(claims.getClaims().keySet()).containsExactlyInAnyOrder("sub", "iat", "exp");
        assertThat(claims.getSubject()).isEqualTo("demo1");
        assertThat(claims.getIssueTime().toInstant()).isEqualTo(issuedAt);
        assertThat(claims.getExpirationTime().toInstant()).isEqualTo(issuedAt.plus(Duration.ofMinutes(15)));
    }

    @Test
    void tokensForDifferentSubjectsDiffer() throws ParseException {
        Instant now = Instant.parse("2026-10-07T10:00:00Z");

        String first = issuer.issue("demo1", now, Duration.ofMinutes(1));
        String second = issuer.issue("demo2", now, Duration.ofMinutes(1));

        assertThat(first).isNotEqualTo(second);
        assertThat(SignedJWT.parse(second).getJWTClaimsSet().getSubject()).isEqualTo("demo2");
    }
}
