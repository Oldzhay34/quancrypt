package com.quancrypt.qbank.account.port.inbound;

/** Returns the public keys that verify tokens issued by this service. */
public interface GetJwksUseCase {

    JwksResult getJwks();
}
