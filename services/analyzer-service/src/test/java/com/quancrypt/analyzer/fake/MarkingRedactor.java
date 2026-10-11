package com.quancrypt.analyzer.fake;

import com.quancrypt.analyzer.port.outbound.Redactor;
import java.util.ArrayList;
import java.util.List;

/**
 * Test redactor: masks every line of a private key block (BEGIN to END, or to the end of the file when END is missing),
 * replaces "secret" with "[REDACTED]" elsewhere, and records the lines it was given.
 */
public final class MarkingRedactor implements Redactor {

    public static final String KEY_MASK = "[REDACTED:private_key_block]";

    private List<String> seen = List.of();

    public List<String> seen() {
        return seen;
    }

    @Override
    public List<String> redactLines(List<String> lines) {
        seen = List.copyOf(lines);
        List<String> out = new ArrayList<>(lines.size());
        boolean inKey = false;
        for (String line : lines) {
            if (!inKey && line.contains("-----BEGIN") && line.contains("PRIVATE KEY-----")) {
                inKey = true;
            }
            if (inKey) {
                out.add(KEY_MASK);
                if (line.contains("-----END") && line.contains("PRIVATE KEY-----")) {
                    inKey = false;
                }
            } else {
                out.add(line.replace("secret", "[REDACTED]"));
            }
        }
        return List.copyOf(out);
    }
}
