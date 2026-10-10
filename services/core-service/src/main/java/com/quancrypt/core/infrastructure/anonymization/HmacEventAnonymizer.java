package com.quancrypt.core.infrastructure.anonymization;

import com.quancrypt.core.domain.event.DomainEvent;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.port.outbound.EventAnonymizer;
import com.quancrypt.core.port.outbound.ProjectKeyHasher;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Anonymizes what leaves core-service (D-20, D-129): the project key is HMAC-SHA256 of the project identity under
 * QUANCRYPT_ANON_SALT, and every string in an event payload passes the redaction rules before it reaches the outbox.
 * Payloads hold coded fields and numbers only; redaction is the second line of defence. The salt lives only here.
 * Key derivation (every implementation must match it, e.g. a Python one): the HMAC key is the UTF-8 bytes of the salt
 * string as given, not a hex decoding of it; the message is the UTF-8 bytes of the identity; the result is lowercase hex.
 */
public final class HmacEventAnonymizer implements EventAnonymizer, ProjectKeyHasher {

    static final String ALGORITHM = "HmacSHA256";
    static final int MIN_SALT_LENGTH = 32;
    static final String PLACEHOLDER = "CHANGE_ME";

    private final SecretKeySpec key;
    private final Redactor redactor;

    public HmacEventAnonymizer(String salt, Redactor redactor) {
        if (salt == null || salt.isBlank() || salt.contains(PLACEHOLDER) || salt.length() < MIN_SALT_LENGTH) {
            throw new IllegalStateException("QUANCRYPT_ANON_SALT must be set to a secret of at least " + MIN_SALT_LENGTH + " characters");
        }
        this.key = new SecretKeySpec(salt.getBytes(StandardCharsets.UTF_8), ALGORITHM);
        this.redactor = redactor;
    }

    @Override
    public ProjectKey hash(String identity) {
        try {
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            return new ProjectKey(HexFormat.of().formatHex(mac.doFinal(identity.getBytes(StandardCharsets.UTF_8))));
        } catch (NoSuchAlgorithmException | InvalidKeyException e) {
            throw new IllegalStateException("HmacSHA256 is mandatory in every JDK", e);
        }
    }

    @Override
    public Map<String, Object> anonymize(DomainEvent event) {
        return redactMap(event.payload());
    }

    private Map<String, Object> redactMap(Map<String, Object> map) {
        Map<String, Object> out = new LinkedHashMap<>();
        map.forEach((k, v) -> out.put(k, redactValue(v)));
        return out;
    }

    @SuppressWarnings("unchecked")
    private Object redactValue(Object value) {
        if (value instanceof String s) {
            return redactor.redact(s);
        }
        if (value instanceof Map<?, ?> nested) {
            return redactMap((Map<String, Object>) nested);
        }
        if (value instanceof List<?> list) {
            List<Object> out = new ArrayList<>();
            list.forEach(item -> out.add(redactValue(item)));
            return out;
        }
        return value;
    }
}
