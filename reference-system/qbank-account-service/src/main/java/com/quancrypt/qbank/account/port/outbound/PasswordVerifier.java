package com.quancrypt.qbank.account.port.outbound;

import com.quancrypt.qbank.account.domain.model.PasswordHash;

/** Checks a raw password against a stored hash. */
public interface PasswordVerifier {

    boolean matches(String rawPassword, PasswordHash hash);
}
