package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

/**
 * Makes a raw text from a project fit the contract's free text fields (finding.schema.json): no control or format
 * characters, at most 256 characters. Detectors build raw names from known tokens; this is the last guard (U3).
 */
public final class NameSanitizer {

    private static final int MAX = 256;

    private NameSanitizer() {
    }

    public static String clean(String text) {
        StringBuilder out = new StringBuilder();
        text.codePoints().forEach(cp -> {
            int type = Character.getType(cp);
            boolean invisible = type == Character.CONTROL || type == Character.FORMAT || type == Character.LINE_SEPARATOR
                    || type == Character.PARAGRAPH_SEPARATOR;
            if (!invisible && out.length() + Character.charCount(cp) <= MAX) {
                out.appendCodePoint(cp);
            }
        });
        String cleaned = out.toString().strip();
        return cleaned.isEmpty() ? "unnamed" : cleaned;
    }
}
