package com.quancrypt.analyzer.unit.domain;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.policy.SensitiveFilePolicy;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class SensitiveFilePolicyTest {

    private final SensitiveFilePolicy policy = new SensitiveFilePolicy();

    @ParameterizedTest
    @ValueSource(strings = {".env", "app/.env", ".env.local", ".ENV.production", "certs/server.p12", "a.PFX", "keystore.jks",
        "x.jceks", "app.keystore", "b.bks", "certs/out/ca.key.pem", "server-key.pem", "tls.key", "home/.ssh/id_rsa", "id_ed25519", "key.der", "a.PK8", "k.p8", "putty.ppk", "home/.netrc", "_netrc", ".pgpass",
        ".git-credentials", "home/.aws/credentials", ".quancrypt/session.token", "sub/.QUANCRYPT/config.yaml"})
    void secretBearingFilesAreRefused(String path) {
        assertThat(policy.isRefused(RelativePath.of(path))).isTrue();
    }

    @ParameterizedTest
    @ValueSource(strings = {"src/main/java/A.java", "application.yml", "certs/out/ca.crt.pem", "jwt-signing.pub.pem", "env.txt",
        "keys/README.md", "id_rsa.pub", "monkey.java"})
    void otherFilesAreServed(String path) {
        assertThat(policy.isRefused(RelativePath.of(path))).isFalse();
    }
}
