package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ScanSummaryView;

/** Reads a scan with finding counts. */
public interface GetScanSummaryUseCase {

    ScanSummaryView execute(GetScanSummaryQuery input);
}
