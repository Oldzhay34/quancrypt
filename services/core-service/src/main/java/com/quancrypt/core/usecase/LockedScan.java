package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.Scan;

/** A scan whose project and consent rows are already locked in the binding order (D-143). */
record LockedScan(Project project, Scan scan, boolean warehouseConsent) {
}
