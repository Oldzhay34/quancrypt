package com.quancrypt.qbank.payment.support;

import com.quancrypt.qbank.payment.infrastructure.crypto.JwkThumbprint;
import com.quancrypt.qbank.payment.infrastructure.crypto.PemKeyLoader;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsExchange;
import com.sun.net.httpserver.HttpsParameters;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.cert.X509Certificate;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;

/**
 * Test double of the QBank account service: an HTTPS server with the real account service certificate that demands
 * a client certificate, publishes the real jwt-signing public key as JWKS and answers account lookups
 * (acc-001 belongs to demo1, acc-002 to demo2, acc-999 does not exist, acc-500 fails, acc-400 is refused, acc-slow answers late and
 * acc-flaky fails once). It records what it received so tests can prove the mTLS identity and the forwarded token.
 */
public final class AccountServiceStub implements AutoCloseable {

    /** One received request. */
    public record Received(String path, String authorization, String clientCertificateSubject, String traceId) {
    }

    private static final Map<String, String> OWNERS = Map.of("acc-001", "demo1", "acc-002", "demo2");

    private final HttpsServer server;
    private final ExecutorService executor = Executors.newCachedThreadPool();
    private final List<Received> received = new CopyOnWriteArrayList<>();
    private final Map<String, AtomicInteger> callCounts = new ConcurrentHashMap<>();
    private final String jwks;

    public AccountServiceStub() {
        RSAPublicKey publicKey = PemKeyLoader.loadPublicKey(TestCertificates.file("jwt-signing.pub.pem"));
        this.jwks = "{\"keys\":[{\"kty\":\"RSA\",\"use\":\"sig\",\"alg\":\"RS256\",\"kid\":\""
                + JwkThumbprint.of(publicKey) + "\",\"n\":\"" + base64Url(publicKey.getModulus().toByteArray())
                + "\",\"e\":\"" + base64Url(publicKey.getPublicExponent().toByteArray()) + "\"}]}";
        try {
            SSLContext context = PemSsl.withIdentity("qbank-account-service.crt.pem", "qbank-account-service.key.pem");
            server = HttpsServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
            server.setHttpsConfigurator(new HttpsConfigurator(context) {
                @Override
                public void configure(HttpsParameters params) {
                    SSLParameters parameters = context.getDefaultSSLParameters();
                    parameters.setNeedClientAuth(true);
                    params.setSSLParameters(parameters);
                }
            });
            server.createContext("/", this::handle);
            server.setExecutor(executor);
            server.start();
        } catch (IOException e) {
            throw new IllegalStateException("cannot start the account service stub", e);
        }
    }

    public int port() {
        return server.getAddress().getPort();
    }

    public String baseUrl() {
        return "https://localhost:" + port();
    }

    public List<Received> received() {
        return List.copyOf(received);
    }

    public long receivedFor(String path) {
        return received.stream().filter(r -> r.path().equals(path)).count();
    }

    @Override
    public void close() {
        server.stop(0);
        executor.shutdownNow();
    }

    private void handle(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        received.add(new Received(
                path,
                exchange.getRequestHeaders().getFirst("Authorization"),
                clientSubject((HttpsExchange) exchange),
                exchange.getRequestHeaders().getFirst("X-Trace-Id")));
        try {
            if (path.equals("/.well-known/jwks.json")) {
                respond(exchange, 200, jwks);
            } else if (path.startsWith("/api/v1/accounts/")) {
                account(exchange, path.substring("/api/v1/accounts/".length()));
            } else {
                respond(exchange, 404, "{}");
            }
        } catch (RuntimeException e) {
            respond(exchange, 500, "{}");
        } finally {
            exchange.close();
        }
    }

    private void account(HttpExchange exchange, String id) throws IOException {
        String authorization = exchange.getRequestHeaders().getFirst("Authorization");
        String subject = subjectOf(authorization);
        if (subject == null) {
            respond(exchange, 401, "{}");
            return;
        }
        int call = callCounts.computeIfAbsent(id, key -> new AtomicInteger()).incrementAndGet();
        switch (id) {
            case "acc-500" -> respond(exchange, 500, "{}");
            case "acc-400" -> respond(exchange, 400, "{}");
            case "acc-flaky" -> {
                if (call == 1) {
                    respond(exchange, 500, "{}");
                } else {
                    respond(exchange, 200, accountJson("acc-flaky"));
                }
            }
            case "acc-slow" -> {
                sleep(2000);
                respond(exchange, 200, accountJson("acc-slow"));
            }
            default -> {
                String owner = OWNERS.get(id);
                if (owner == null) {
                    respond(exchange, 404, "{}");
                } else if (!owner.equals(subject)) {
                    respond(exchange, 403, "{}");
                } else {
                    respond(exchange, 200, accountJson(id));
                }
            }
        }
    }

    private static String accountJson(String id) {
        return "{\"accountId\":\"" + id + "\",\"ownerName\":\"Demo\",\"currency\":\"TRY\",\"balance\":\"1000.00\"}";
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    private static String clientSubject(HttpsExchange exchange) {
        try {
            return ((X509Certificate) exchange.getSSLSession().getPeerCertificates()[0])
                    .getSubjectX500Principal().getName();
        } catch (SSLPeerUnverifiedException e) {
            return null;
        }
    }

    /** The "sub" claim of an unverified bearer token (the real account service verifies the signature). */
    private static String subjectOf(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return null;
        }
        String[] parts = authorization.substring("Bearer ".length()).split("\\.");
        if (parts.length != 3) {
            return null;
        }
        String payload;
        try {
            payload = new String(Base64.getUrlDecoder().decode(parts[1]), StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            return null;
        }
        int start = payload.indexOf("\"sub\":\"");
        if (start < 0) {
            return null;
        }
        int from = start + "\"sub\":\"".length();
        return payload.substring(from, payload.indexOf('"', from));
    }

    private static String base64Url(byte[] bytes) {
        int start = bytes.length > 1 && bytes[0] == 0 ? 1 : 0;
        return Base64.getUrlEncoder().withoutPadding().encodeToString(java.util.Arrays.copyOfRange(bytes, start, bytes.length));
    }

    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
