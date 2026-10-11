package com.quancrypt.core.facade.dto;

import java.time.Instant;

/** Privacy notice (schema PrivacyNotice). */
public record PrivacyNoticeDto(int version, String textTr, String textEn, Instant publishedAt) {
}
