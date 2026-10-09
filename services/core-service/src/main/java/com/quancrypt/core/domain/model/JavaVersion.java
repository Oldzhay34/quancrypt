package com.quancrypt.core.domain.model;

import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Major version of a project's Java runtime; parsed from strings such as 25.0.4.1, 17.0.2+8 or 1.8.0_302. */
public record JavaVersion(int major) {

    private static final Pattern LEADING_MAJOR = Pattern.compile("^(?:1\\.)?(\\d+)");

    public JavaVersion {
        if (major < 1) {
            throw new IllegalArgumentException("major version must be positive");
        }
    }

    /** Empty when the text does not start with a version number. */
    public static Optional<JavaVersion> parse(String text) {
        if (text == null) {
            return Optional.empty();
        }
        Matcher matcher = LEADING_MAJOR.matcher(text.trim());
        if (!matcher.find()) {
            return Optional.empty();
        }
        int major = Integer.parseInt(matcher.group(1));
        return major < 1 ? Optional.empty() : Optional.of(new JavaVersion(major));
    }

    public boolean isAtLeast(int required) {
        return major >= required;
    }
}
