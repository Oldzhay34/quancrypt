package com.quancrypt.qbank.gateway.support;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
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

    public Response get(String path, String bearerToken) throws IOException, InterruptedException {
        return send("GET", path, bearerToken, Map.of(), null);
    }

    public Response postJson(String path, String bearerToken, Map<String, String> headers, String json)
            throws IOException, InterruptedException {
        Map<String, String> all = new LinkedHashMap<>(headers);
        all.put("Content-Type", "application/json");
        return send("POST", path, bearerToken, all, json);
    }

    /** A POST without a body, such as the receipt request. */
    public Response postEmpty(String path, String bearerToken, Map<String, String> headers)
            throws IOException, InterruptedException {
        return send("POST", path, bearerToken, headers, null);
    }

    public Response send(String method, String path, String bearerToken, Map<String, String> headers, String body)
            throws IOException, InterruptedException {
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create("https://localhost:" + port + path))
                .timeout(Duration.ofSeconds(15))
                .method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body));
        if (bearerToken != null) {
            request.header("Authorization", "Bearer " + bearerToken);
        }
        headers.forEach(request::header);
        HttpResponse<String> response = client.send(request.build(), HttpResponse.BodyHandlers.ofString());
        return new Response(
                response.statusCode(),
                response.headers().firstValue("Content-Type").orElse(null),
                response.headers().firstValue("X-Trace-Id").orElse(null),
                response.body());
    }
}
