package com.quancrypt.core.domain.model;

/** Kind of the caller of a command (bearerAuth or X-Internal-Token). */
public enum CallerKind {
    UI,
    INTERNAL;
}
