package com.quancrypt.core.domain.model;

import java.time.Instant;
import java.util.UUID;

/** A versioned privacy notice text in Turkish and English (FR-03). */
public record PrivacyNotice(UUID id, int version, String textTr, String textEn, Instant publishedAt) {
}
