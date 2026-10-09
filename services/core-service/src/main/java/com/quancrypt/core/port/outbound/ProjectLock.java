package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Project;
import java.util.Optional;
import java.util.UUID;

/** Row locks on a project in the order of the binding lock rule (D-143). */
public interface ProjectLock {

    /** FOR KEY SHARE: event writers and tree writers take this first (D-143). */
    Optional<Project> keyShare(UUID projectId);

    /** FOR NO KEY UPDATE: serializes runtime profile writers. */
    Optional<Project> noKeyUpdate(UUID projectId);

    /** FOR UPDATE: only DeleteProject. */
    Optional<Project> update(UUID projectId);
}
