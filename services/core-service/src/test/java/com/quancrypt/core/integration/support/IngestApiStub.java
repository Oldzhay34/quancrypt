package com.quancrypt.core.integration.support;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

/** A loopback HTTP server standing in for ingest-api (P6.1): it records request bodies and answers a settable status. */
public final class IngestApiStub implements AutoCloseable {

    public static final String PATH = "/api/v1/events";

    private final HttpServer server;
    private final AtomicInteger status = new AtomicInteger(202);
    private final List<String> bodies = new CopyOnWriteArrayList<>();
    private final List<String> tokens = new CopyOnWriteArrayList<>();

    public IngestApiStub() {
        try {
            server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        server.createContext(PATH, exchange -> {
            try (InputStream in = exchange.getRequestBody()) {
                bodies.add(new String(in.readAllBytes(), StandardCharsets.UTF_8));
            }
            tokens.add(String.valueOf(exchange.getRequestHeaders().getFirst("X-Internal-Token")));
            exchange.sendResponseHeaders(status.get(), -1);
            exchange.close();
        });
        server.start();
    }

    public String url() {
        return "http://" + server.getAddress().getHostString() + ":" + server.getAddress().getPort() + PATH;
    }

    public void answer(int statusCode) {
        status.set(statusCode);
    }

    public List<String> bodies() {
        return List.copyOf(bodies);
    }

    /** The X-Internal-Token header of every request received ("null" when it had none). */
    public List<String> tokens() {
        return List.copyOf(tokens);
    }

    public void reset() {
        bodies.clear();
        tokens.clear();
        status.set(202);
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
