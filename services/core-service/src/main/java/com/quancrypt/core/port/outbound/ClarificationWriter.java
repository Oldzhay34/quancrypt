package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.ClarificationAnswer;
import java.util.List;
import java.util.UUID;

/** Writes clarification answers. */
public interface ClarificationWriter {

    void upsertAll(UUID projectId, List<ClarificationAnswer> answers);
}
