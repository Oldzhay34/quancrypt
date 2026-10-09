package com.quancrypt.core.port.inbound.view;

import java.util.Optional;

/** A project with its current runtime profile. */
public record ProjectDetailView(ProjectView project, Optional<RuntimeProfileView> currentRuntimeProfile) {
}
