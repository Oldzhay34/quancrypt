package com.quancrypt.core.domain.model;

/** A finding together with its source file (path, scan, kind). */
public record FindingDetail(Finding finding, SourceFile file) {
}
