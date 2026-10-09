package com.quancrypt.core.port.inbound;

import java.util.UUID;

/** Reads the model of a scan's plan report. */
public record GetPlanReportQuery(UUID scanId) {
}
