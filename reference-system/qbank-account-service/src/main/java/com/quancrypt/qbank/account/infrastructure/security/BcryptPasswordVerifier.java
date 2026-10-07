package com.quancrypt.qbank.account.infrastructure.security;

import com.quancrypt.qbank.account.domain.model.PasswordHash;
import com.quancrypt.qbank.account.port.outbound.PasswordVerifier;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

/** Checks passwords against BCrypt hashes. */
public class BcryptPasswordVerifier implements PasswordVerifier {

    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    @Override
    public boolean matches(String rawPassword, PasswordHash hash) {
        if (rawPassword == null || hash == null) {
            return false;
        }
        return encoder.matches(rawPassword, hash.value());
    }
}
