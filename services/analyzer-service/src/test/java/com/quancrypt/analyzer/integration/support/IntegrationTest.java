package com.quancrypt.analyzer.integration.support;

import com.quancrypt.analyzer.AnalyzerServiceApplication;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Base of the Spring integration tests: the real composition root (infrastructure/config) behind a real HTTP port, with a
 * random service token and two allowed directories, the QBank reference system and a scratch directory for projects a
 * test writes itself. The token has no default in the service, so every run uses its own.
 */
@SpringBootTest(classes = AnalyzerServiceApplication.class, webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
public abstract class IntegrationTest {

    private static final SecureRandom RANDOM = new SecureRandom();
    protected static final String INTERNAL_TOKEN = randomToken();
    protected static final Path REFERENCE = Path.of(System.getProperty("quancrypt.reference.dir")).toAbsolutePath().normalize();
    protected static final Path SCRATCH = scratch();

    @Value("${local.server.port}")
    protected int port;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("quancrypt.internal-token", () -> INTERNAL_TOKEN);
        registry.add("analyzer.allowed-roots", () -> REFERENCE + "," + SCRATCH);
    }

    protected ApiClient api() {
        return new ApiClient(port);
    }

    private static String randomToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static Path scratch() {
        try {
            return Files.createTempDirectory("analyzer-it-").toRealPath();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
