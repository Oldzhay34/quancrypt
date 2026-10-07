package com.quancrypt.qbank.account.support;

import com.quancrypt.qbank.account.domain.model.VerificationKey;
import com.quancrypt.qbank.account.port.outbound.VerificationKeySource;
import java.math.BigInteger;
import java.util.List;

/** Test double: one fixed key. */
public final class FakeVerificationKeySource implements VerificationKeySource {

    public static final VerificationKey KEY =
            new VerificationKey("fake-key-id", BigInteger.valueOf(0x00c0ffeeL), BigInteger.valueOf(65537));

    @Override
    public List<VerificationKey> verificationKeys() {
        return List.of(KEY);
    }
}
