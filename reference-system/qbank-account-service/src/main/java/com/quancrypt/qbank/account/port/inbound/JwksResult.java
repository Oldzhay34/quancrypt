package com.quancrypt.qbank.account.port.inbound;

import java.math.BigInteger;
import java.util.List;

/** The set of public verification keys. */
public record JwksResult(List<Key> keys) {

    public JwksResult {
        keys = List.copyOf(keys);
    }

    /** One RSA public key. */
    public record Key(String keyId, BigInteger modulus, BigInteger exponent) {
    }
}
