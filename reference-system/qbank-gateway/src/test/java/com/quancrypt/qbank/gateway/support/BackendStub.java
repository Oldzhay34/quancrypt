package com.quancrypt.qbank.gateway.support;

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
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLPeerUnverifiedException;

/**
 * Test double of a QBank back end: an HTTPS server with the real certificate of the service it stands for that
 * demands a client certificate (mutual TLS), records what it received and answers with its own name so that a test
 * can tell which route reached it.
 */
public final class BackendStub implements AutoCloseable {

    /** One received request. */
    public record Received(
            String method, String path, String clientCertificateSubject, String traceId, String authorization,
            String forwardedHost, String body) {
    }

    private final String name;
    private final HttpsServer server;
    private final ExecutorService executor = Executors.newCachedThreadPool();
    private final List<Received> received = new CopyOnWriteArrayList<>();

    /** @param name the name carried in the answer; @param certificateBase file name (without .crt.pem/.key.pem) of its server identity */
    public BackendStub(String name, String certificateBase) {
        this.name = name;
        try {
            SSLContext context = PemSsl.withIdentity(certificateBase + ".crt.pem", certificateBase + ".key.pem");
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
            throw new IllegalStateException("cannot start the back end stub " + name, e);
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

    @Override
    public void close() {
        server.stop(0);
        executor.shutdownNow();
    }

    private void handle(HttpExchange exchange) throws IOException {
        try {
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            received.add(new Received(
                    exchange.getRequestMethod(),
                    exchange.getRequestURI().getPath(),
                    clientSubject((HttpsExchange) exchange),
                    exchange.getRequestHeaders().getFirst("X-Trace-Id"),
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    exchange.getRequestHeaders().getFirst("X-Forwarded-Host"),
                    body));
            String traceId = exchange.getRequestHeaders().getFirst("X-Trace-Id");
            if (traceId != null) {
                exchange.getResponseHeaders().set("X-Trace-Id", traceId);
            }
            byte[] answer = ("{\"backend\":\"" + name + "\"}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, answer.length);
            exchange.getResponseBody().write(answer);
        } finally {
            exchange.close();
        }
    }

    private static String clientSubject(HttpsExchange exchange) {
        try {
            return ((X509Certificate) exchange.getSSLSession().getPeerCertificates()[0])
                    .getSubjectX500Principal().getName();
        } catch (SSLPeerUnverifiedException e) {
            return null;
        }
    }
}
