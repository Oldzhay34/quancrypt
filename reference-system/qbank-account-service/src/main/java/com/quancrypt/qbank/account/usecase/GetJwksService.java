package com.quancrypt.qbank.account.usecase;

import com.quancrypt.qbank.account.port.inbound.GetJwksUseCase;
import com.quancrypt.qbank.account.port.inbound.JwksResult;
import com.quancrypt.qbank.account.port.outbound.VerificationKeySource;
import java.util.Objects;

/** Publishes the public keys that verify issued tokens. */
public final class GetJwksService implements GetJwksUseCase {

    private final VerificationKeySource keySource;

    public GetJwksService(VerificationKeySource keySource) {
        this.keySource = Objects.requireNonNull(keySource, "keySource");
    }

    @Override
    public JwksResult getJwks() {
        return new JwksResult(keySource.verificationKeys().stream()
                .map(key -> new JwksResult.Key(key.keyId(), key.modulus(), key.exponent()))
                .toList());
    }
}
