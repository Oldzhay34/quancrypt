package com.quancrypt.qbank.account.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.qbank.account.support.ServiceClient;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** Health endpoints live on the plain-HTTP management port, not on the mutual-TLS main port (D-88). */
class ManagementEndpointsTest extends ServiceIntegrationTest {

    private final HttpClient plainHttp = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();

    private HttpResponse<String> managementGet(String path) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + managementPort() + path))
                .timeout(Duration.ofSeconds(5)).GET().build();
        return plainHttp.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @ParameterizedTest
    @ValueSource(strings = {"/health/liveness", "/health/readiness"})
    void theProbesReportUpOverPlainHttpWithoutAClientCertificate(String path) throws Exception {
        HttpResponse<String> response = managementGet(path);

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("\"status\":\"UP\"");
    }

    @ParameterizedTest
    @ValueSource(strings = {"/actuator", "/actuator/health", "/actuator/env", "/env", "/beans"})
    void nothingButTheHealthGroupIsExposed(String path) throws Exception {
        assertThat(managementGet(path).statusCode()).isEqualTo(404);
    }

    @Test
    void theManagementPortDoesNotSpeakTls() {
        ServiceClient tlsClient = new ServiceClient(sslContext("gwaccount"), managementPort());

        assertThatThrownBy(() -> tlsClient.get("/health/liveness", null)).isInstanceOf(IOException.class);
    }

    @Test
    void theMainPortDoesNotServeHealthEndpoints() throws Exception {
        assertThat(gatewayClient().get("/health/liveness", null).status()).isEqualTo(404);
    }

    @Test
    void theMainPortIsNotReachableOverPlainHttp() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port() + "/.well-known/jwks.json"))
                .timeout(Duration.ofSeconds(5)).GET().build();

        HttpResponse<String> response = plainHttp.send(request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(400);
        assertThat(response.body()).doesNotContain("keys");
    }
}
