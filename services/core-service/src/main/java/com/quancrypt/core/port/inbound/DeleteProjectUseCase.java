package com.quancrypt.core.port.inbound;

/** Deletes a project; revocation events are written first (D-127). */
public interface DeleteProjectUseCase {

    void execute(DeleteProjectCommand input);
}
