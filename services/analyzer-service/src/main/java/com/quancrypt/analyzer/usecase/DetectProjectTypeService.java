package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.port.inbound.DetectProjectTypeCommand;
import com.quancrypt.analyzer.port.inbound.DetectProjectTypeUseCase;
import com.quancrypt.analyzer.port.inbound.ProjectView;
import java.util.Objects;

/** Finds the build system of a project under an allowed root. */
public final class DetectProjectTypeService implements DetectProjectTypeUseCase {

    private final ProjectOpener opener;

    public DetectProjectTypeService(ProjectOpener opener) {
        this.opener = Objects.requireNonNull(opener, "opener");
    }

    @Override
    public ProjectView detect(DetectProjectTypeCommand command) {
        return Views.project(opener.open(command.root()).descriptor());
    }
}
