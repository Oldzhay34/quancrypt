package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.LocationKind;

/** A source file path with the kind the caller says it has. */
record PathKind(String path, LocationKind kind) {
}
