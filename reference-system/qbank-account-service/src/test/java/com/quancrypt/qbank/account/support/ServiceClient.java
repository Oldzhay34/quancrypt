package com.quancrypt.qbank.account.support;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import javax.net.ssl.SSLContext;

/** Minimal HTTPS client for the integration tests; it fails on TLS errors instead of hiding them. */
public final class ServiceClient {

    /** A received response. */
    public record Response(int status, String contentType, String traceId, String body) {
    }

    private final HttpClient client;
    private final int port;

    public ServiceClient(SSLContext sslContext, int port) {
        this.client = HttpClient.newBuilder().sslContext(sslContext).connectTimeout(Duration.ofSeconds(10)).build();
        this.port = port;
    }

    public Response get(String path, String bearerToken, String traceId) throws IOException, InterruptedException {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path)).GET().timeout(Duration.ofSeconds(10));
        if (bearerToken != null) {
            request.header("Authorization", "Bearer " + bearerToken);
        }
        if (traceId != null) {
            request.header("X-Trace-Id", traceId);
        }
        return send(request.build());
    }

    public Response get(String path, String bearerToken) throws IOException, InterruptedException {
        return get(path, bearerToken, null);
    }

    public Response postJson(String path, String json) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(uri(path))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .timeout(Duration.ofSeconds(10))
                .build();
        return send(request);
    }

    public Response send(HttpRequest request) throws IOException, InterruptedException {
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        return new Response(
                response.statusCode(),
                response.headers().firstValue("Content-Type").orElse(null),
                response.headers().firstValue("X-Trace-Id").orElse(null),
                response.body());
    }

    private URI uri(String path) {
        return URI.create("https://localhost:" + port + path);
    }
}
