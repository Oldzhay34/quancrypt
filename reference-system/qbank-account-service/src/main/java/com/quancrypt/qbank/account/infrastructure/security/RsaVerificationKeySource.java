package com.quancrypt.qbank.account.infrastructure.security;

import com.quancrypt.qbank.account.domain.model.VerificationKey;
import com.quancrypt.qbank.account.port.outbound.VerificationKeySource;
import java.util.List;

/** Provides the public key of the token signing key pair. */
public class RsaVerificationKeySource implements VerificationKeySource {

    private final VerificationKey key;

    public RsaVerificationKeySource(JwtKeyMaterial keys) {
        this.key = new VerificationKey(
                keys.keyId(), keys.publicKey().getModulus(), keys.publicKey().getPublicExponent());
    }

    @Override
    public List<VerificationKey> verificationKeys() {
        return List.of(key);
    }
}
