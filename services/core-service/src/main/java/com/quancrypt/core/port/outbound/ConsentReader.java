package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.ConsentType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Reads consents. */
public interface ConsentReader {

    Optional<Consent> find(UUID projectId, ConsentType type);

    List<Consent> list(UUID projectId);
}
