package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.Optional;

/** A crypto library the project depends on, read from a build file (facts for the CBOM, P3.3). */
public record LibraryDependency(RelativePath file, String group, String artifact, Optional<String> version, int line) {
}
