package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Reads a scan with finding counts. */
public record GetScanSummaryQuery(UUID scanId) {
}
