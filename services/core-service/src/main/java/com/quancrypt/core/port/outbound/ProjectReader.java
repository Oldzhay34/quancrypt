package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import java.util.Optional;
import java.util.UUID;

/** Reads projects. */
public interface ProjectReader {

    Optional<Project> findById(UUID projectId);

    Optional<Project> findByKey(ProjectKey key);

    PageResult<Project> page(int page, int size);
}
