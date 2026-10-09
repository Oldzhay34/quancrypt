package com.quancrypt.core.port.inbound.view;

import java.time.Instant;

/** The latest privacy notice. */
public record PrivacyNoticeView(int version, String textTr, String textEn, Instant publishedAt) {
}
