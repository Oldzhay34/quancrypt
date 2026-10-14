package com.quancrypt.analyzer.infrastructure.plugin.javaspring.file;

import java.util.Optional;

/** A dependency written in a build file: coordinates, the version as written (possibly a property reference) and its line. */
record BuildDependency(String group, String artifact, Optional<String> version, int line) {
}
