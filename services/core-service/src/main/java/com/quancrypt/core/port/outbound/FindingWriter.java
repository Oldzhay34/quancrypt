package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Finding;
import java.util.List;
import java.util.UUID;

/** Writes findings. */
public interface FindingWriter {

    /** Inserts the findings that do not exist yet (same file, symbol, algorithm, context and line) and returns their ids. */
    List<UUID> insertIgnoringDuplicates(List<Finding> findings);
}
