package com.quancrypt.qbank.gateway.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.gateway.support.BackendStub;
import com.quancrypt.qbank.gateway.support.PemSsl;
import com.quancrypt.qbank.gateway.support.ServiceClient;
import java.io.IOException;
import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Map;
import javax.net.ssl.SSLSocket;
import org.junit.jupiter.api.Test;

/** Routes, the mutual TLS identity towards the back ends and the TLS the gateway offers to external clients. */
class GatewayRoutingTest extends GatewayIntegrationTest {

    private static final String BACKEND_IDENTITY = "CN=gateway-to-account,O=QBank Demo";

    private static BackendStub.Received lastOf(BackendStub stub) {
        List<BackendStub.Received> all = stub.received();
        return all.get(all.size() - 1);
    }

    @Test
    void accountRoutesReachTheAccountServiceOverMutualTls() throws Exception {
        ServiceClient client = externalClient();

        ServiceClient.Response login = client.postJson("/api/v1/auth/login", null, Map.of(), "{}");
        assertThat(login.status()).isEqualTo(200);
        assertThat(login.body()).contains("\"backend\":\"account\"");
        assertThat(lastOf(ACCOUNT).path()).isEqualTo("/api/v1/auth/login");

        assertThat(client.get("/api/v1/accounts/acc-001", "token").body()).contains("\"backend\":\"account\"");
        assertThat(lastOf(ACCOUNT).path()).isEqualTo("/api/v1/accounts/acc-001");

        assertThat(client.get("/.well-known/jwks.json", null).body()).contains("\"backend\":\"account\"");
        assertThat(lastOf(ACCOUNT).path()).isEqualTo("/.well-known/jwks.json");

        assertThat(ACCOUNT.received()).allSatisfy(r -> assertThat(r.clientCertificateSubject()).isEqualTo(BACKEND_IDENTITY));
    }

    @Test
    void paymentRoutesReachThePaymentServiceWithTheSameClientIdentity() throws Exception {
        ServiceClient client = externalClient();

        String body = "{\"accountId\":\"acc-001\"}";
        ServiceClient.Response created = client.postJson(
                "/api/v1/payments", "the-token", Map.of("Idempotency-Key", "k-1"), body);
        assertThat(created.status()).isEqualTo(200);
        assertThat(created.body()).contains("\"backend\":\"payment\"");
        BackendStub.Received received = lastOf(PAYMENT);
        assertThat(received.method()).isEqualTo("POST");
        assertThat(received.path()).isEqualTo("/api/v1/payments");
        assertThat(received.body()).isEqualTo(body);
        assertThat(received.authorization()).isEqualTo("Bearer the-token");

        assertThat(client.get("/api/v1/payments/abc", "the-token").body()).contains("\"backend\":\"payment\"");
        assertThat(lastOf(PAYMENT).path()).isEqualTo("/api/v1/payments/abc");
        assertThat(client.postEmpty("/api/v1/payments/abc/receipt", "the-token", Map.of()).body())
                .contains("\"backend\":\"payment\"");
        assertThat(lastOf(PAYMENT).path()).isEqualTo("/api/v1/payments/abc/receipt");

        assertThat(PAYMENT.received()).allSatisfy(r -> assertThat(r.clientCertificateSubject()).isEqualTo(BACKEND_IDENTITY));
    }

    @Test
    void theTraceIdIsPassedToTheBackEndAndBack() throws Exception {
        ServiceClient.Response response = externalClient()
                .send("GET", "/api/v1/accounts/acc-001", "token", Map.of("X-Trace-Id", "trace-from-client"), null);

        assertThat(lastOf(ACCOUNT).traceId()).isEqualTo("trace-from-client");
        assertThat(response.traceId()).isEqualTo("trace-from-client");
    }

    @Test
    void pathsThatNoRouteOwnsAreNotFoundAndNeverReachABackEnd() throws Exception {
        int accountBefore = ACCOUNT.received().size();
        int paymentBefore = PAYMENT.received().size();
        ServiceClient client = externalClient();

        assertThat(client.get("/no/such/path", null).status()).isEqualTo(404);
        assertThat(client.get("/api/v1/other", "token").status()).isEqualTo(404);
        assertThat(client.get("/health", null).status()).as("health lives on the management port only").isEqualTo(404);
        assertThat(client.get("/actuator/health", null).status()).isEqualTo(404);

        assertThat(ACCOUNT.received()).hasSize(accountBefore);
        assertThat(PAYMENT.received()).hasSize(paymentBefore);
    }

    @Test
    void externalClientsNeedNoCertificateButGetTheGatewayServerCertificate() throws Exception {
        try (SSLSocket socket = (SSLSocket) PemSsl.trustOnly().getSocketFactory()
                .createSocket(InetAddress.getLoopbackAddress(), port())) {
            socket.startHandshake();
            X509Certificate certificate = (X509Certificate) socket.getSession().getPeerCertificates()[0];

            assertThat(certificate.getSubjectX500Principal().getName()).isEqualTo("CN=qbank-gateway,O=QBank Demo");
            assertThat(socket.getSession().getProtocol()).isIn("TLSv1.3", "TLSv1.2");
        }
    }

    @Test
    void plainHttpOnTheTlsPortGetsNoAnswerFromABackEnd() throws Exception {
        int accountBefore = ACCOUNT.received().size();
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://localhost:" + port() + "/api/v1/accounts/acc-001"))
                .build();

        try {
            HttpResponse<String> response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
            assertThat(response.statusCode()).isGreaterThanOrEqualTo(400);
        } catch (IOException expected) {
            // refused or reset: the TLS port does not speak plain HTTP; the check that matters is below
        }

        assertThat(ACCOUNT.received()).hasSize(accountBefore);
    }

    @Test
    void aClientThatDoesNotTrustTheDemoCaCannotConnect() {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(URI.create("https://localhost:" + port() + "/api/v1/accounts/acc-001"))
                .build();

        assertThatThrownBy(() -> client.send(request, HttpResponse.BodyHandlers.ofString()))
                .isInstanceOf(IOException.class);
    }
}
