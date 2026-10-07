package com.quancrypt.qbank.gateway.integration;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;

/** Health lives on a plain-HTTP management port; nothing else is exposed there. */
class ManagementEndpointsTest extends GatewayIntegrationTest {

    private int statusOf(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + managementPort() + path)).build();
        return HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString()).statusCode();
    }

    @Test
    void livenessAndReadinessAreUp() throws Exception {
        assertThat(statusOf("/health/liveness")).isEqualTo(200);
        assertThat(statusOf("/health/readiness")).isEqualTo(200);
        assertThat(statusOf("/health")).isEqualTo(200);
    }

    @Test
    void noOtherEndpointIsExposed() throws Exception {
        assertThat(statusOf("/env")).isEqualTo(404);
        assertThat(statusOf("/beans")).isEqualTo(404);
        assertThat(statusOf("/gateway/routes")).isEqualTo(404);
        assertThat(statusOf("/actuator")).isEqualTo(404);
    }
}
