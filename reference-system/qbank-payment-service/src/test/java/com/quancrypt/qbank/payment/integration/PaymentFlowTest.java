package com.quancrypt.qbank.payment.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.payment.infrastructure.crypto.JwkThumbprint;
import com.quancrypt.qbank.payment.infrastructure.crypto.PemKeyLoader;
import com.quancrypt.qbank.payment.support.AccountServiceStub;
import com.quancrypt.qbank.payment.support.ServiceClient;
import com.quancrypt.qbank.payment.support.TestCertificates;
import com.quancrypt.qbank.payment.support.TokenFactory;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** mTLS, JWT validation, the account service call and the receipt signature, end to end over real TLS. */
class PaymentFlowTest extends ServiceIntegrationTest {

    private static final String CARD = "4111111111111111";
    private static final String PAYMENT_BODY =
            "{\"accountId\":\"acc-001\",\"amount\":\"12.50\",\"currency\":\"TRY\",\"cardNumber\":\"" + CARD + "\"}";

    private final TokenFactory tokens = new TokenFactory();
    private final JsonMapper json = JsonMapper.builder().build();

    private ServiceClient.Response createPayment(String token, String key, String body) throws Exception {
        Map<String, String> headers = key == null ? Map.of() : Map.of("Idempotency-Key", key);
        return gatewayClient().postJson("/api/v1/payments", token, headers, body);
    }

    private String createdPaymentId() throws Exception {
        ServiceClient.Response created = createPayment(tokens.valid("demo1"), null, PAYMENT_BODY);
        assertThat(created.status()).isEqualTo(201);
        return json.readTree(created.body()).get("paymentId").asString();
    }

    @Test
    void withoutAClientCertificateEveryEndpointIsRejectedAtTlsLevel() throws Exception {
        ServiceClient client = clientWithoutCertificate();
        String token = tokens.valid("demo1");

        assertThatThrownBy(() -> client.postJson("/api/v1/payments", token, Map.of(), PAYMENT_BODY))
                .isInstanceOf(IOException.class);
        assertThatThrownBy(() -> client.get("/api/v1/payments/" + new java.util.UUID(0, 1), token))
                .isInstanceOf(IOException.class);
        assertThatThrownBy(() -> client.postEmpty("/api/v1/payments/" + new java.util.UUID(0, 1) + "/receipt", token, Map.of()))
                .isInstanceOf(IOException.class);

        // control: the same request succeeds when a client certificate is presented
        assertThat(createPayment(token, null, PAYMENT_BODY).status()).isEqualTo(201);
    }

    @Test
    void aCertificateThatIsNotValidForClientAuthenticationIsRejected() {
        ServiceClient client = clientWithServerCertificate();

        assertThatThrownBy(() -> client.get("/api/v1/payments/" + new java.util.UUID(0, 1), tokens.valid("demo1")))
                .isInstanceOf(IOException.class);
    }

    @Test
    void requestsWithoutAJwtAreRejectedWith401() throws Exception {
        ServiceClient client = gatewayClient();
        String id = new java.util.UUID(0, 1).toString();

        for (ServiceClient.Response response : List.of(
                client.postJson("/api/v1/payments", null, Map.of(), PAYMENT_BODY),
                client.get("/api/v1/payments/" + id, null),
                client.postEmpty("/api/v1/payments/" + id + "/receipt", null, Map.of()),
                client.get("/no/such/path", null))) {
            assertThat(response.status()).isEqualTo(401);
            assertThat(response.contentType()).startsWith("application/problem+json");
            assertThat(response.traceId()).isNotBlank();
        }
    }

    @Test
    void forgedAndInvalidJwtsAreRejectedWith401() throws Exception {
        String[] bad = {
            tokens.expired("demo1"),
            tokens.signedByAnotherKey("demo1"),
            tokens.unsecured("demo1"),
            tokens.hs256WithPublicKeyAsSecret("demo1"),
            tokens.withoutSubject(),
            tokens.withoutExpiry("demo1"),
            "garbage",
        };
        for (String token : bad) {
            ServiceClient.Response response = createPayment(token, null, PAYMENT_BODY);
            assertThat(response.status()).as("token %s...", token.substring(0, Math.min(10, token.length()))).isEqualTo(401);
            assertThat(response.contentType()).startsWith("application/problem+json");
        }
    }

    @Test
    void aValidJwtCreatesAPaymentAndTheServiceTalksToTheAccountServiceWithItsOwnClientCertificate() throws Exception {
        String token = tokens.valid("demo1");

        ServiceClient.Response response = createPayment(token, null, PAYMENT_BODY);

        assertThat(response.status()).isEqualTo(201);
        JsonNode body = json.readTree(response.body());
        assertThat(body.get("accountId").asString()).isEqualTo("acc-001");
        assertThat(body.get("amount").asString()).isEqualTo("12.50");
        assertThat(body.get("currency").asString()).isEqualTo("TRY");
        assertThat(body.get("paymentId").asString()).matches("[0-9a-f-]{36}");
        assertThat(body.get("createdAt").asString()).endsWith("Z");

        List<AccountServiceStub.Received> lookups = ACCOUNT_SERVICE.received().stream()
                .filter(r -> r.path().equals("/api/v1/accounts/acc-001") && ("Bearer " + token).equals(r.authorization()))
                .toList();
        assertThat(lookups).as("the caller's token was forwarded to the account service").hasSize(1);
        assertThat(lookups.get(0).clientCertificateSubject()).contains("CN=payment-to-account");
        assertThat(ACCOUNT_SERVICE.received()).anySatisfy(r -> {
            assertThat(r.path()).isEqualTo("/.well-known/jwks.json");
            assertThat(r.clientCertificateSubject()).contains("CN=payment-to-account");
        });
    }

    @Test
    void theResponseNeverContainsTheCardNumberOrAToken() throws Exception {
        ServiceClient.Response response = createPayment(tokens.valid("demo1"), null, PAYMENT_BODY);

        assertThat(response.body()).doesNotContain(CARD).doesNotContain("cardNumber").doesNotContain("cardToken");
        String id = json.readTree(response.body()).get("paymentId").asString();
        ServiceClient.Response fetched = gatewayClient().get("/api/v1/payments/" + id, tokens.valid("demo1"));
        assertThat(fetched.status()).isEqualTo(200);
        assertThat(fetched.body()).isEqualTo(response.body());
    }

    @Test
    void accountProblemsOfTheAccountServiceBecomeProblemsOfThePaymentService() throws Exception {
        String token = tokens.valid("demo1");

        assertThat(createPayment(token, null, PAYMENT_BODY.replace("acc-001", "acc-002")).status()).isEqualTo(403);
        assertThat(createPayment(token, null, PAYMENT_BODY.replace("acc-001", "acc-999")).status()).isEqualTo(404);
        // The 503 case (account service failing) lives in ApiContractTest only: failing calls count against the shared
        // circuit breaker, and two classes doing it back to back could open it for the other tests.
    }

    @Test
    void theSameIdempotencyKeyReturnsTheSamePaymentAndADifferentRequestIsAConflict() throws Exception {
        String token = tokens.valid("demo1");
        String key = "flow-key-" + System.nanoTime();

        ServiceClient.Response first = createPayment(token, key, PAYMENT_BODY);
        ServiceClient.Response again = createPayment(token, key, PAYMENT_BODY);
        ServiceClient.Response different = createPayment(token, key, PAYMENT_BODY.replace("12.50", "13.50"));

        assertThat(first.status()).isEqualTo(201);
        assertThat(again.status()).isEqualTo(201);
        assertThat(again.body()).isEqualTo(first.body());
        assertThat(different.status()).isEqualTo(409);
        assertThat(json.readTree(different.body()).get("type").asString())
                .isEqualTo("https://quancrypt.local/problems/idempotency-conflict");
    }

    @Test
    void malformedPaymentRequestsAreRejectedWith400() throws Exception {
        String token = tokens.valid("demo1");
        String[] bad = {
            "{}",
            PAYMENT_BODY.replace("12.50", "12.5"),
            PAYMENT_BODY.replace("TRY", "try"),
            PAYMENT_BODY.replace(CARD, "4111-1111"),
            PAYMENT_BODY.replace("acc-001", "a".repeat(65)),
            PAYMENT_BODY.replace("acc-001", "acc/001"),
            PAYMENT_BODY.replace("acc-001", "acc 001"),
            PAYMENT_BODY.replace("}", ",\"role\":\"admin\"}"),
            "not json",
        };
        for (String body : bad) {
            assertThat(createPayment(token, null, body).status()).as(body).isEqualTo(400);
        }
        assertThat(createPayment(token, "", PAYMENT_BODY).status()).isEqualTo(400);
    }

    @Test
    void anUnknownPaymentIs404AndSoIsAnIdThatIsNotAUuid() throws Exception {
        String token = tokens.valid("demo1");

        assertThat(gatewayClient().get("/api/v1/payments/" + new java.util.UUID(0, 99), token).status()).isEqualTo(404);
        assertThat(gatewayClient().get("/api/v1/payments/not-a-uuid", token).status()).isEqualTo(404);
        assertThat(gatewayClient().postEmpty("/api/v1/payments/" + new java.util.UUID(0, 99) + "/receipt", token, Map.of())
                .status()).isEqualTo(404);
    }

    @Test
    void theReceiptSignatureVerifiesWithTheRsa1024PublicKeyOverTheCompactJsonOfTheReceipt() throws Exception {
        String token = tokens.valid("demo1");
        String paymentId = createdPaymentId();

        ServiceClient.Response response = gatewayClient().postEmpty("/api/v1/payments/" + paymentId + "/receipt", token, Map.of());

        assertThat(response.status()).isEqualTo(200);
        JsonNode body = json.readTree(response.body());
        assertThat(body.get("algorithm").asString()).isEqualTo("SHA1withRSA");
        JsonNode receipt = body.get("receipt");
        String signingInput = "{\"paymentId\":\"" + receipt.get("paymentId").asString()
                + "\",\"accountId\":\"" + receipt.get("accountId").asString()
                + "\",\"amount\":\"" + receipt.get("amount").asString()
                + "\",\"currency\":\"" + receipt.get("currency").asString()
                + "\",\"issuedAt\":\"" + receipt.get("issuedAt").asString() + "\"}";
        RSAPublicKey publicKey = PemKeyLoader.loadPublicKey(TestCertificates.file("receipt-signing.pub.pem"));
        assertThat(publicKey.getModulus().bitLength()).isEqualTo(1024);
        assertThat(body.get("keyId").asString()).isEqualTo(JwkThumbprint.of(publicKey));
        assertThat(verifies(publicKey, "SHA1withRSA", signingInput, body.get("signature").asString())).isTrue();
        assertThat(verifies(publicKey, "SHA1withRSA", signingInput.replace("12.50", "99.99"), body.get("signature").asString()))
                .isFalse();
        assertThat(receipt.get("paymentId").asString()).isEqualTo(paymentId);
        assertThat(receipt.get("accountId").asString()).isEqualTo("acc-001");
    }

    @Test
    void receiptsWithTheSameIdempotencyKeyAreIdenticalAndAnotherPaymentConflicts() throws Exception {
        String token = tokens.valid("demo1");
        String paymentId = createdPaymentId();
        String otherPaymentId = createdPaymentId();
        String key = "receipt-key-" + System.nanoTime();
        String path = "/api/v1/payments/" + paymentId + "/receipt";

        ServiceClient.Response first = gatewayClient().postEmpty(path, token, Map.of("Idempotency-Key", key));
        ServiceClient.Response again = gatewayClient().postEmpty(path, token, Map.of("Idempotency-Key", key));
        ServiceClient.Response conflict = gatewayClient().postEmpty(
                "/api/v1/payments/" + otherPaymentId + "/receipt", token, Map.of("Idempotency-Key", key));

        assertThat(first.status()).isEqualTo(200);
        assertThat(again.body()).isEqualTo(first.body());
        assertThat(conflict.status()).isEqualTo(409);
    }

    @Test
    void theHandshakeUsesTlsOneThreeOrTwo() throws Exception {
        try (javax.net.ssl.SSLSocket socket = (javax.net.ssl.SSLSocket) gatewaySslContext().getSocketFactory()
                .createSocket("localhost", port())) {
            socket.startHandshake();

            assertThat(socket.getSession().getProtocol()).isIn("TLSv1.3", "TLSv1.2");
            assertThat(((java.security.cert.X509Certificate) socket.getSession().getPeerCertificates()[0])
                    .getSubjectX500Principal().getName()).contains("CN=qbank-payment-service");
        }
    }

    private static boolean verifies(RSAPublicKey key, String algorithm, String text, String signatureBase64)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(key);
        verifier.update(text.getBytes(StandardCharsets.UTF_8));
        return verifier.verify(Base64.getDecoder().decode(signatureBase64));
    }
}
