package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Project;
import java.util.UUID;

/** Writes projects. */
public interface ProjectWriter {

    /** Inserts the project unless one with the same key exists; returns whether it was inserted. */
    boolean insertIfAbsent(Project project);

    /** Deletes the project and, by cascade, everything under it. */
    void delete(UUID projectId);
}
