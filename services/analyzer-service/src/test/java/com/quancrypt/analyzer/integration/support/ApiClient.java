package com.quancrypt.analyzer.integration.support;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** A plain HTTP client for the running service: headers and bodies exactly as a caller sends them (no Spring on the client side). */
public final class ApiClient {

    /** A response: status, headers (lower-case names), raw body. */
    public record Reply(int status, Map<String, String> headers, byte[] body) {

        public String text() {
            return new String(body, StandardCharsets.UTF_8);
        }

        public JsonNode json() {
            return JSON.readTree(body);
        }

        public String header(String name) {
            return headers.get(name.toLowerCase());
        }
    }

    public static final JsonMapper JSON = JsonMapper.builder().build();

    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private final String baseUrl;

    public ApiClient(int port) {
        this.baseUrl = "http://127.0.0.1:" + port;
    }

    /** A request under construction: header by header, then send. */
    public final class Call {
        private final String method;
        private final String path;
        private final Map<String, String> headers = new LinkedHashMap<>();
        private byte[] body;

        private Call(String method, String path) {
            this.method = method;
            this.path = path;
        }

        public Call header(String name, String value) {
            headers.put(name, value);
            return this;
        }

        public Call bearer(String token) {
            return header("Authorization", "Bearer " + token);
        }

        public Call internal(String token) {
            return header("X-Internal-Token", token);
        }

        public Call json(Object payload) {
            this.body = JSON.writeValueAsBytes(payload);
            return header("Content-Type", "application/json");
        }

        public Call body(byte[] content, String contentType) {
            this.body = content;
            return header("Content-Type", contentType);
        }

        public Reply send() {
            HttpRequest.Builder request = HttpRequest.newBuilder(URI.create(baseUrl + path)).timeout(Duration.ofSeconds(60));
            headers.forEach(request::header);
            request.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofByteArray(body));
            try {
                HttpResponse<byte[]> response = http.send(request.build(), HttpResponse.BodyHandlers.ofByteArray());
                Map<String, String> replyHeaders = new LinkedHashMap<>();
                response.headers().map().forEach((k, v) -> replyHeaders.put(k.toLowerCase(), String.join(", ", v)));
                return new Reply(response.statusCode(), replyHeaders, response.body());
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        }
    }

    public Call call(String method, String path) {
        return new Call(method, path);
    }

    public Call get(String path) {
        return new Call("GET", path);
    }

    public Call post(String path) {
        return new Call("POST", path);
    }

    public Call put(String path) {
        return new Call("PUT", path);
    }

    public Call delete(String path) {
        return new Call("DELETE", path);
    }

    public Call options(String path) {
        return new Call("OPTIONS", path);
    }
}
