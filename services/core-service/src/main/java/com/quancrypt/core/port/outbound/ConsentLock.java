package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Row locks on consents. */
public interface ConsentLock {

    /** FOR SHARE on the consent row of a type (any state); event writers read it this way (D-21). */
    Optional<Consent> share(UUID projectId, ConsentType type);

    /** FOR UPDATE on every consent row of a project; only DeleteProject. */
    List<Consent> updateAll(UUID projectId);
}
