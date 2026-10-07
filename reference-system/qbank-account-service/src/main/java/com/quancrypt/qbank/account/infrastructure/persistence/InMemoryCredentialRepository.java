package com.quancrypt.qbank.account.infrastructure.persistence;

import com.quancrypt.qbank.account.domain.model.UserCredential;
import com.quancrypt.qbank.account.port.outbound.CredentialRepository;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/** Holds user credentials in memory; the contents are fixed at construction time. */
public final class InMemoryCredentialRepository implements CredentialRepository {

    private final Map<String, UserCredential> credentials = new LinkedHashMap<>();

    public InMemoryCredentialRepository(Collection<UserCredential> initialCredentials) {
        for (UserCredential credential : initialCredentials) {
            if (credentials.putIfAbsent(credential.username(), credential) != null) {
                throw new IllegalArgumentException("duplicate username");
            }
        }
    }

    @Override
    public Optional<UserCredential> findByUsername(String username) {
        return Optional.ofNullable(credentials.get(username));
    }
}
