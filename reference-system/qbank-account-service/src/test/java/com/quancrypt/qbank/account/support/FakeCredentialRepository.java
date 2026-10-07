package com.quancrypt.qbank.account.support;

import com.quancrypt.qbank.account.domain.model.UserCredential;
import com.quancrypt.qbank.account.port.outbound.CredentialRepository;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

/** Test double backed by a map. */
public final class FakeCredentialRepository implements CredentialRepository {

    private final Map<String, UserCredential> credentials = new HashMap<>();

    public FakeCredentialRepository(UserCredential... initial) {
        for (UserCredential credential : initial) {
            credentials.put(credential.username(), credential);
        }
    }

    @Override
    public Optional<UserCredential> findByUsername(String username) {
        return Optional.ofNullable(credentials.get(username));
    }
}
