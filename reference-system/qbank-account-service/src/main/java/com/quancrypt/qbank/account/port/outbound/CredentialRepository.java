package com.quancrypt.qbank.account.port.outbound;

import com.quancrypt.qbank.account.domain.model.UserCredential;
import java.util.Optional;

/** Read access to user credentials. */
public interface CredentialRepository {

    Optional<UserCredential> findByUsername(String username);
}
