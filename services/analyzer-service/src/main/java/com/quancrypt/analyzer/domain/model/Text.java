package com.quancrypt.analyzer.domain.model;

import java.util.Optional;
import java.util.regex.Pattern;

/** Shared checks of the value objects; every failure is an IllegalArgumentException with a fixed message. */
final class Text {

    static final Pattern TOKEN = Pattern.compile("[A-Za-z0-9._/+()#-]{1,128}");
    static final Pattern VERSION = Pattern.compile("[0-9A-Za-z._+-]{1,32}");
    static final Pattern IDENTIFIER = Pattern.compile("[a-z0-9.-]{1,64}");
    static final Pattern NODE_ID = Pattern.compile("[A-Za-z0-9._-]{1,200}");

    private Text() {
    }

    /** A string of 1 to {@code max} characters without control characters. */
    static String printable(String value, int max, String field) {
        if (value == null || value.isEmpty() || value.length() > max || hasControl(value)) {
            throw new IllegalArgumentException(field + " must be 1 to " + max + " characters without control or format characters");
        }
        return value;
    }

    static String matching(String value, Pattern pattern, String field) {
        if (value == null || !pattern.matcher(value).matches()) {
            throw new IllegalArgumentException(field + " has an invalid format");
        }
        return value;
    }

    static Optional<String> optionalMatching(Optional<String> value, Pattern pattern, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        value.ifPresent(v -> matching(v, pattern, field));
        return value;
    }

    /**
     * Whether the value holds a character that is invisible or reorders text: C0/C1 controls and DEL (CONTROL),
     * bidirectional and zero-width marks (FORMAT), and line or paragraph separators.
     */
    static boolean hasControl(String value) {
        return value.codePoints().anyMatch(cp -> {
            int type = Character.getType(cp);
            return type == Character.CONTROL || type == Character.FORMAT || type == Character.LINE_SEPARATOR
                    || type == Character.PARAGRAPH_SEPARATOR;
        });
    }
}
