package com.quancrypt.analyzer.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.port.outbound.Redactor;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * The contract every Redactor keeps (D-179): the line count never changes, and every line of a private key block is
 * masked, whether or not the block has an END line. The real adapter (P3.3, contracts/redaction-rules.yaml) must pass
 * this class too.
 */
public abstract class RedactorContract {

    protected abstract Redactor redactor();

    private static final List<String> KEY_BODY = List.of(
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj",
            "MzEfYyjiWA4R4/M2bS1GB4t7NXp98C3SC6dVMvDuictGeurT8jNbvJZHtCSuYEvu",
            "NMoSfm76oqFvAp8Gy0iz5sxjZmSnXyCdPEovGhLa0VzMaQ8s+CLOyS56YyCFGeJZ",
            "aZpKRKtZ5hbh1w==");

    private static List<String> file(boolean withEnd) {
        List<String> lines = new ArrayList<>();
        lines.add("before: plain");
        lines.add("-----BEGIN PRIVATE KEY-----");
        lines.addAll(KEY_BODY);
        if (withEnd) {
            lines.add("-----END PRIVATE KEY-----");
            lines.add("after: plain");
        }
        return lines;
    }

    @Test
    void theLineCountNeverChanges() {
        assertThat(redactor().redactLines(file(true))).hasSize(file(true).size());
        assertThat(redactor().redactLines(List.of())).isEmpty();
        assertThat(redactor().redactLines(List.of("", "x"))).hasSize(2);
    }

    @Test
    void everyLineOfAPrivateKeyBlockIsMasked() {
        List<String> redacted = redactor().redactLines(file(true));

        for (String body : KEY_BODY) {
            assertThat(redacted).noneMatch(line -> line.contains(body));
        }
        assertThat(redacted.get(0)).isEqualTo("before: plain");
        assertThat(redacted.get(redacted.size() - 1)).isEqualTo("after: plain");
    }

    @Test
    void aBlockWithoutAnEndLineIsMaskedToTheEndOfTheFile() {
        List<String> redacted = redactor().redactLines(file(false));

        for (String body : KEY_BODY) {
            assertThat(redacted).noneMatch(line -> line.contains(body));
        }
    }

    @Test
    void aFileAboveTheSharedInputLimitKeepsItsLineCountAndItsKeyMasked() {
        // contracts/redaction-rules.yaml max_input_length is 1 MiB; files may be up to 5 MiB (D-181). Redacting in chunks is
        // not allowed: a key block on a chunk border would escape.
        List<String> lines = new ArrayList<>();
        for (int i = 0; i < 20_000; i++) {
            lines.add("filler line " + i + " ".repeat(48));
        }
        lines.addAll(file(true));

        List<String> redacted = redactor().redactLines(lines);

        assertThat(redacted).hasSize(lines.size());
        for (String body : KEY_BODY) {
            assertThat(redacted).noneMatch(line -> line.contains(body));
        }
    }
}
