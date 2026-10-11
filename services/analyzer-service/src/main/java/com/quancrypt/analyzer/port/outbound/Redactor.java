package com.quancrypt.analyzer.port.outbound;

import java.util.List;

/**
 * Masks secrets with the shared rules of contracts/redaction-rules.yaml (D-179). The rules run over the whole text of a
 * file, so a match spanning lines (a private key block) is found; every line a match touches is masked.
 */
public interface Redactor {

    /** The lines of a whole file, redacted; the result has exactly as many lines as the input. */
    List<String> redactLines(List<String> lines);
}
