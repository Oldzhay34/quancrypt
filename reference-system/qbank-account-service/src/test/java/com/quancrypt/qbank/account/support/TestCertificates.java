package com.quancrypt.qbank.account.support;

import java.nio.file.Files;
import java.nio.file.Path;

/** Locates the PEM files that reference-system/certs/generate.sh produced. */
public final class TestCertificates {

    private TestCertificates() {
    }

    /** The certificate directory; fails with an actionable message when it does not exist. */
    public static Path dir() {
        String configured = System.getProperty("qbank.certs.dir");
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException("system property qbank.certs.dir is not set");
        }
        Path dir = Path.of(configured).toAbsolutePath().normalize();
        if (!Files.isDirectory(dir) || !Files.isRegularFile(dir.resolve("ca.crt.pem"))) {
            throw new IllegalStateException(
                    "certificates not found in " + dir + "; run `make certs` (reference-system/certs/generate.sh)");
        }
        return dir;
    }

    public static Path file(String name) {
        return dir().resolve(name);
    }
}
