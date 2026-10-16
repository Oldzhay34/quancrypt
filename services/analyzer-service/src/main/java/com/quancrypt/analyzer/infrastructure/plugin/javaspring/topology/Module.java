package com.quancrypt.analyzer.infrastructure.plugin.javaspring.topology;

import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.config.ConfigProperty;
import java.util.Locale;
import java.util.Optional;

/**
 * A module of the project: a directory with a build file, its application name and its Spring configuration. {@code dir} is
 * empty for a build file at the root of the analyzed tree.
 */
public record Module(String dir, String name, ModuleConfig config, Optional<String> javaVersion) {

    /** What a module's server side says about TLS (Spring Boot {@code server.ssl.*}). */
    public record Server(boolean tls, Optional<String> bundle, ClientAuth clientAuth, int port, Optional<ConfigProperty> sslProperty) {
    }

    /** Client certificate handling of a TLS server. */
    public enum ClientAuth {
        NONE, WANT, NEED;

        /** Whether the server asks clients for a certificate, which makes the connection mutual TLS when the client has one. */
        public boolean asksForCertificate() {
            return this != NONE;
        }
    }

    public boolean contains(RelativePath file) {
        return dir.isEmpty() || file.value().startsWith(dir + "/");
    }

    /** The directory's own name, or the application name for a root module. */
    public String directoryName() {
        if (dir.isEmpty()) {
            return name;
        }
        return dir.substring(dir.lastIndexOf('/') + 1);
    }

    public boolean isGateway() {
        return config.hasKeyStartingWith("spring.cloud.gateway");
    }

    public Server server() {
        Optional<String> bundle = config.value("server.ssl.bundle").filter(v -> !v.isEmpty());
        boolean enabledFlag = config.value("server.ssl.enabled").map(v -> !v.equalsIgnoreCase("false")).orElse(true);
        boolean certificate = bundle.isPresent() || config.property("server.ssl.key-store").isPresent()
                || config.property("server.ssl.certificate").isPresent();
        ClientAuth auth = config.value("server.ssl.client-auth").map(v -> switch (v.toLowerCase(Locale.ROOT)) {
            case "need" -> ClientAuth.NEED;
            case "want" -> ClientAuth.WANT;
            default -> ClientAuth.NONE;
        }).orElse(ClientAuth.NONE);
        int port = config.value("server.port").flatMap(Module::port).orElse(8080);
        Optional<ConfigProperty> property = config.property("server.ssl.bundle").or(() -> config.property("server.ssl.key-store"))
                .or(() -> config.property("server.ssl.certificate"));
        return new Server(enabledFlag && certificate, bundle, auth, port, property);
    }

    private static Optional<Integer> port(String value) {
        try {
            int port = Integer.parseInt(value.strip());
            return port > 0 && port <= 65535 ? Optional.of(port) : Optional.empty();
        } catch (NumberFormatException e) {
            return Optional.empty();
        }
    }
}
