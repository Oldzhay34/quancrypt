package com.quancrypt.analyzer.domain.model;

import java.util.Objects;

/** An analyzed project: its root and build system; plugins decide from it whether they support the project. */
public record ProjectDescriptor(AnalysisRoot root, ProjectType type) {

    public ProjectDescriptor {
        Objects.requireNonNull(root, "root");
        Objects.requireNonNull(type, "type");
    }
}
