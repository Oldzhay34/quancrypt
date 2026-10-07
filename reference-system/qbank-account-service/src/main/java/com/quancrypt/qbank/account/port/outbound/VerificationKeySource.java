package com.quancrypt.qbank.account.port.outbound;

import com.quancrypt.qbank.account.domain.model.VerificationKey;
import java.util.List;

/** Provides the public keys that verify issued tokens. */
public interface VerificationKeySource {

    /** Returns at least one key. */
    List<VerificationKey> verificationKeys();
}
