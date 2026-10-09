package com.quancrypt.core.port.inbound;

/** Idempotency key and request digest of a command; the digest covers method, path template, path parameters and body (D-136). */
public record Idempotency(String key, String requestDigest) {
}
