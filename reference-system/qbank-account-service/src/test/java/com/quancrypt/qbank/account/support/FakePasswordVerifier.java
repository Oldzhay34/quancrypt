package com.quancrypt.qbank.account.support;

import com.quancrypt.qbank.account.domain.model.PasswordHash;
import com.quancrypt.qbank.account.port.outbound.PasswordVerifier;

/** Test double: the "hash" is the password with a prefix. */
public final class FakePasswordVerifier implements PasswordVerifier {

    public static PasswordHash hashOf(String rawPassword) {
        return new PasswordHash("fake:" + rawPassword);
    }

    @Override
    public boolean matches(String rawPassword, PasswordHash hash) {
        return rawPassword != null && hash != null && hash.value().equals("fake:" + rawPassword);
    }
}
