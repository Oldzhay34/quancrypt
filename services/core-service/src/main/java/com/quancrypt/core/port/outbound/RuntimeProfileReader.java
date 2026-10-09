package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.RuntimeProfile;
import java.util.Optional;
import java.util.UUID;

/** Reads the runtime profile history of a project. */
public interface RuntimeProfileReader {

    Optional<RuntimeProfile> current(UUID projectId);

    Optional<RuntimeProfile> bySequence(UUID projectId, int sequenceNo);
}
