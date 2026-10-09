package com.quancrypt.core.domain.model;

import java.util.regex.Pattern;

/** HMAC-SHA256 of the project identity as 64 lowercase hex characters; the only project identity stored (D-129). */
public record ProjectKey(String value) {

    private static final Pattern HEX64 = Pattern.compile("^[0-9a-f]{64}$");

    public ProjectKey {
        if (value == null || !HEX64.matcher(value).matches()) {
            throw new IllegalArgumentException("project key must be 64 lowercase hex characters");
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
