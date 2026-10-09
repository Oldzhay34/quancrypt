package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.ClarificationAnswer;
import java.util.List;
import java.util.UUID;

/** Reads clarification answers. */
public interface ClarificationReader {

    List<ClarificationAnswer> list(UUID projectId);
}
