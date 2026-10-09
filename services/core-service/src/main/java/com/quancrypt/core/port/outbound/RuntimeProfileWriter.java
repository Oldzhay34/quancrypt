package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.RuntimeProfile;
import java.util.UUID;

/** Appends to the runtime profile history. */
public interface RuntimeProfileWriter {

    void insert(UUID projectId, RuntimeProfile profile);
}
