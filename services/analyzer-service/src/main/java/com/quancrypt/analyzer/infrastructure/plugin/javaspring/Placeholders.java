package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import java.util.Optional;
import java.util.function.Function;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Resolves Spring style placeholders ${key} and ${key:default} in configuration values. */
public final class Placeholders {

    private static final Pattern PLACEHOLDER = Pattern.compile("\\$\\{([^${}:]+)(?::([^${}]*))?}");
    private static final int MAX_ROUNDS = 5;
    /** A longer value is returned as written and an expansion that grows past it stops: ${a} chains must not multiply. */
    static final int MAX_LENGTH = 8192;

    private Placeholders() {
    }

    /** The value with every resolvable placeholder replaced; the others stay as written. */
    public static String resolve(String value, Function<String, Optional<String>> lookup) {
        String current = value;
        if (value.length() > MAX_LENGTH) {
            return value;
        }
        for (int round = 0; round < MAX_ROUNDS && current.contains("${"); round++) {
            Matcher matcher = PLACEHOLDER.matcher(current);
            StringBuilder out = new StringBuilder();
            boolean changed = false;
            while (matcher.find()) {
                Optional<String> replacement = lookup.apply(matcher.group(1)).or(() -> Optional.ofNullable(matcher.group(2)));
                if (replacement.isPresent()) {
                    changed = true;
                    matcher.appendReplacement(out, Matcher.quoteReplacement(replacement.get()));
                } else {
                    matcher.appendReplacement(out, Matcher.quoteReplacement(matcher.group()));
                }
                if (out.length() > MAX_LENGTH) {
                    return current;
                }
            }
            matcher.appendTail(out);
            if (out.length() > MAX_LENGTH) {
                return current;
            }
            current = out.toString();
            if (!changed) {
                break;
            }
        }
        return current;
    }
}
