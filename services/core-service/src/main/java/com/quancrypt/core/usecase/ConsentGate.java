package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.port.outbound.ConsentLock;
import java.util.UUID;

/** Tells whether warehouse events may be written; reads the consent row FOR SHARE so a revoke cannot slip in (D-21). */
public final class ConsentGate {

    private final ConsentLock consentLock;

    public ConsentGate(ConsentLock consentLock) {
        this.consentLock = consentLock;
    }

    boolean warehouseConsented(UUID projectId) {
        return consentLock.share(projectId, ConsentType.WAREHOUSE_ANALYTICS).filter(Consent::isActive).isPresent();
    }
}
