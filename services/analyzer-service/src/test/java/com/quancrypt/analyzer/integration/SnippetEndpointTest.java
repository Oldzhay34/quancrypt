package com.quancrypt.analyzer.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.integration.support.ApiClient.Reply;
import com.quancrypt.analyzer.integration.support.IntegrationTest;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * The snippet endpoint end to end (guardrails-security sections 3 and 5): secrets in the file never reach the response, a
 * private key block is masked even when the window starts inside it, and files that carry secrets are not served at all.
 */
class SnippetEndpointTest extends IntegrationTest {

    private static final String PASSWORD = "hunter2-hunter2-value";
    private static final List<String> KEY_BODY = List.of("MIIEvQIBADANBgkqhkiG9w0BAQEFAASCnotarealkeyjusttestdata", "AbCdEfGhIjKlMnOpQrSt");

    private static Path project;

    @BeforeAll
    static void project() throws Exception {
        project = Files.createDirectory(SCRATCH.resolve("snippet-project"));
        Files.writeString(project.resolve("application.properties"),
                "server.port=8443\ndb.password=" + PASSWORD + "\nnote=plain\n");
        Files.writeString(project.resolve("notes.txt"), String.join("\n", "intro", "-----BEGIN PRIVATE KEY-----", KEY_BODY.get(0),
                KEY_BODY.get(1), "-----END PRIVATE KEY-----", "outro") + "\n");
        Files.writeString(project.resolve(".env"), "API_TOKEN=" + PASSWORD + "\n");
        Files.writeString(project.resolve("server.key.pem"), "-----BEGIN PRIVATE KEY-----\n" + KEY_BODY.get(0) + "\n-----END PRIVATE KEY-----\n");
    }

    private Reply snippet(String path, int line, int context) {
        String query = "root=" + URLEncoder.encode(project.toString(), StandardCharsets.UTF_8) + "&path=" + URLEncoder.encode(path, StandardCharsets.UTF_8)
                + "&line=" + line + "&context=" + context;
        return api().get("/api/v1/snippets?" + query).internal(INTERNAL_TOKEN).send();
    }

    @Test
    void anAssignedSecretIsMaskedAndTheRestOfTheLineKept() {
        Reply reply = snippet("application.properties", 2, 1);

        assertThat(reply.status()).isEqualTo(200);
        assertThat(reply.text()).doesNotContain(PASSWORD).contains("[REDACTED:").contains("server.port=8443").contains("note=plain");
    }

    @Test
    void aPrivateKeyBlockIsMaskedEvenWhenTheWindowStartsInsideIt() {
        Reply insideOnly = snippet("notes.txt", 4, 0);
        Reply whole = snippet("notes.txt", 4, 10);

        for (Reply reply : List.of(insideOnly, whole)) {
            assertThat(reply.status()).isEqualTo(200);
            KEY_BODY.forEach(body -> assertThat(reply.text()).doesNotContain(body));
        }
        assertThat(insideOnly.json().get("lines").get(0).get("text").asString()).contains("[REDACTED:private_key_block]");
        assertThat(whole.text()).contains("intro").contains("outro");
    }

    @Test
    void filesThatCarrySecretsAreNotServed() {
        for (String path : List.of(".env", "server.key.pem")) {
            Reply reply = snippet(path, 1, 0);

            assertThat(reply.status()).as(path).isEqualTo(400);
            assertThat(reply.json().get("type").asString()).isEqualTo("https://quancrypt.local/problems/path-not-allowed");
            assertThat(reply.text()).doesNotContain(PASSWORD).doesNotContain(KEY_BODY.get(0));
        }
    }

    @Test
    void aLinePastTheEndOfTheFileIsNotFound() {
        assertThat(snippet("application.properties", 99, 0).status()).isEqualTo(404);
    }
}
