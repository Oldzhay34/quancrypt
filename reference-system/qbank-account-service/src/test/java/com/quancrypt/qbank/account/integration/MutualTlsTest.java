package com.quancrypt.qbank.account.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.SignedJWT;
import com.quancrypt.qbank.account.support.ServiceClient;
import com.quancrypt.qbank.account.support.TokenFactory;
import java.io.IOException;
import java.security.cert.X509Certificate;
import java.text.ParseException;
import javax.net.ssl.SSLSocket;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** The service accepts only clients with a certificate from the demo CA (D-80) and issues verifiable RS256 tokens. */
class MutualTlsTest extends ServiceIntegrationTest {

    private final TokenFactory tokens = new TokenFactory(TokenFactory.realKeys());
    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void withoutAClientCertificateEveryEndpointIsRejectedAtTlsLevel() throws Exception {
        ServiceClient noCertificate = clientFor("nocert");
        String token = tokens.valid("demo1");

        assertThatThrownBy(() -> noCertificate.postJson("/api/v1/auth/login", LOGIN_BODY_DEMO1))
                .isInstanceOf(IOException.class);
        assertThatThrownBy(() -> noCertificate.get("/.well-known/jwks.json", null)).isInstanceOf(IOException.class);
        assertThatThrownBy(() -> noCertificate.get("/api/v1/accounts/acc-001", token)).isInstanceOf(IOException.class);

        // control: the same requests succeed at the application level when a client certificate is presented
        assertThat(gatewayClient().get("/.well-known/jwks.json", null).status()).isEqualTo(200);
    }

    @Test
    void aCertificateThatIsNotValidForClientAuthenticationIsRejected() {
        ServiceClient serverCertificateAsClient = clientFor("servercert");

        assertThatThrownBy(() -> serverCertificateAsClient.get("/.well-known/jwks.json", null))
                .isInstanceOf(IOException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"gwaccount", "gwpayment", "payaccount"})
    void everyDemoClientCertificateIsAccepted(String bundle) throws Exception {
        assertThat(clientFor(bundle).get("/.well-known/jwks.json", null).status()).isEqualTo(200);
    }

    @Test
    void theHandshakeUsesTlsOneThreeOrTwoAndTheServerCertificateOfTheAccountService() throws Exception {
        try (SSLSocket socket = (SSLSocket) sslContext("gwaccount").getSocketFactory().createSocket("localhost", port())) {
            socket.startHandshake();

            assertThat(socket.getSession().getProtocol()).isIn("TLSv1.3", "TLSv1.2");
            X509Certificate peer = (X509Certificate) socket.getSession().getPeerCertificates()[0];
            assertThat(peer.getSubjectX500Principal().getName()).contains("CN=qbank-account-service");
        }
    }

    @Test
    void loginIssuesAnRs256TokenThatTheJwksVerifies() throws Exception {
        ServiceClient client = gatewayClient();

        ServiceClient.Response login = client.postJson("/api/v1/auth/login", LOGIN_BODY_DEMO1);
        ServiceClient.Response jwksResponse = client.get("/.well-known/jwks.json", null);

        assertThat(login.status()).isEqualTo(200);
        JsonNode loginBody = json.readTree(login.body());
        assertThat(loginBody.get("tokenType").asString()).isEqualTo("Bearer");
        assertThat(loginBody.get("expiresIn").asLong()).isEqualTo(900);

        SignedJWT jwt = SignedJWT.parse(loginBody.get("accessToken").asString());
        assertThat(jwt.getHeader().getAlgorithm()).isEqualTo(JWSAlgorithm.RS256);
        String keyId = jwt.getHeader().getKeyID();
        assertThat(keyId).isNotBlank();

        RSAKey key = (RSAKey) JWKSet.parse(jwksResponse.body()).getKeyByKeyId(keyId);
        assertThat(key).as("the JWKS contains the key named in the token header").isNotNull();
        assertThat(jwt.verify(new RSASSAVerifier(key))).isTrue();
        assertThat(jwt.getJWTClaimsSet().getSubject()).isEqualTo("demo1");
        long lifetimeSeconds = (jwt.getJWTClaimsSet().getExpirationTime().getTime()
                - jwt.getJWTClaimsSet().getIssueTime().getTime()) / 1000;
        assertThat(lifetimeSeconds).isEqualTo(900);
    }

    @Test
    void theTokenFromLoginOpensTheOwnAccount() throws Exception {
        ServiceClient client = gatewayClient();
        String token = json.readTree(client.postJson("/api/v1/auth/login", LOGIN_BODY_DEMO1).body())
                .get("accessToken").asString();

        ServiceClient.Response own = client.get("/api/v1/accounts/acc-001", token);
        ServiceClient.Response other = client.get("/api/v1/accounts/acc-002", token);

        assertThat(own.status()).isEqualTo(200);
        assertThat(json.readTree(own.body()).get("balance").asString()).isEqualTo("1000.00");
        assertThat(other.status()).isEqualTo(403);
    }

    @Test
    void everyDemoPasswordMatchesItsStoredHash() throws Exception {
        ServiceClient client = gatewayClient();
        for (int i = 1; i <= 3; i++) {
            String body = "{\"username\":\"demo" + i + "\",\"password\":\"demo" + i + "-demo-pass\"}";
            assertThat(client.postJson("/api/v1/auth/login", body).status()).as("demo" + i).isEqualTo(200);
        }
        assertThat(client.postJson("/api/v1/auth/login",
                "{\"username\":\"demo1\",\"password\":\"demo2-demo-pass\"}").status()).isEqualTo(401);
    }

    @Test
    void forgedAndInvalidTokensAreRejectedWithA401() throws Exception {
        ServiceClient client = gatewayClient();
        String[] bad = {
            tokens.expired("demo1"),
            tokens.withKeyId("demo1", "other-key-id"),
            tokens.signedByAnotherKey("demo1"),
            tokens.withTamperedSignature("demo1"),
            tokens.unsecured("demo1"),
            tokens.hs256WithPublicKeyAsSecret("demo1"),
            tokens.withoutExpiry("demo1"),
            tokens.withoutSubject(),
            "garbage",
        };
        for (String token : bad) {
            ServiceClient.Response response = client.get("/api/v1/accounts/acc-001", token);
            assertThat(response.status()).as("token %s...", token.substring(0, Math.min(12, token.length()))).isEqualTo(401);
            assertThat(response.contentType()).startsWith("application/problem+json");
        }
        assertThat(client.get("/api/v1/accounts/acc-001", null).status()).isEqualTo(401);
    }

    @Test
    void aValidTokenForAnUnknownAccountIs404AndForAMalformedAccountId400() throws Exception {
        ServiceClient client = gatewayClient();
        String token = tokens.valid("demo1");

        assertThat(client.get("/api/v1/accounts/acc-999", token).status()).isEqualTo(404);
        assertThat(client.get("/api/v1/accounts/" + "a".repeat(65), token).status()).isEqualTo(400);
    }

    @Test
    void aTokenOfAnUnknownUserIsAuthenticDeniedNotAuthenticated() throws Exception {
        ServiceClient.Response response = gatewayClient().get("/api/v1/accounts/acc-001", tokens.valid("ghost"));

        assertThat(response.status()).isEqualTo(403);
    }

    @Test
    void jwksParsesAsAJwkSet() throws ParseException, IOException, InterruptedException {
        JWKSet set = JWKSet.parse(gatewayClient().get("/.well-known/jwks.json", null).body());

        assertThat(set.getKeys()).hasSize(1);
        assertThat(set.getKeys().get(0)).isInstanceOf(RSAKey.class);
    }
}
