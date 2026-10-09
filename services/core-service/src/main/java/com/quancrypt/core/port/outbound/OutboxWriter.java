package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.ProjectKey;

/** Writes the transactional outbox. */
public interface OutboxWriter {

    void append(OutboxRecord record);

    /** Deletes the project's unsent events except revocations (D-147); returns how many. */
    int deletePendingExceptRevocations(ProjectKey projectKey);
}
