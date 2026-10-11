package com.quancrypt.core.facade;

import com.quancrypt.core.port.inbound.Idempotency;
import com.quancrypt.core.port.inbound.RequestDigest;
import java.util.Optional;

/** Builds the idempotency information of a command: the key and a digest of method, path template, path parameters and body (D-136). */
final class Idem {

    private Idem() {
    }

    /** The text of the body is its toString(): the inputs are records, so equal bodies print equally. */
    static Optional<Idempotency> of(Optional<String> key, String method, String pathTemplate, Object body, String... pathParameters) {
        return key.map(k -> {
            String[] parts = new String[3 + pathParameters.length + 1];
            parts[0] = method;
            parts[1] = pathTemplate;
            parts[2] = String.valueOf(pathParameters.length);
            System.arraycopy(pathParameters, 0, parts, 3, pathParameters.length);
            parts[parts.length - 1] = body == null ? "" : body.toString();
            return new Idempotency(k, RequestDigest.of(parts));
        });
    }
}
