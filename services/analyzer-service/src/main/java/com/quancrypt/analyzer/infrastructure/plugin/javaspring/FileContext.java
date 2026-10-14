package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import java.util.Optional;

/** The file a detector is looking at; Java files come with their parsed unit. */
public record FileContext(ProjectFile file, Optional<JavaUnit> unit) {

    public JavaUnit java() {
        return unit.orElseThrow(() -> new IllegalStateException("not a parsed Java file"));
    }
}
