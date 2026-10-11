package com.quancrypt.analyzer.domain.model;

import java.util.Objects;
import java.util.Optional;

/** Where something was seen: a file, its lines (empty when the whole file is meant) and the kind of source. */
public record Evidence(RelativePath file, Optional<LineRange> lines, LocationKind locationKind) {

    public Evidence {
        Objects.requireNonNull(file, "file");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(locationKind, "locationKind");
    }
}
