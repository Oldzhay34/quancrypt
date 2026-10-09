package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ScanView;

/** Finishes a running scan. */
public interface CompleteScanUseCase {

    ScanView execute(CompleteScanCommand input);
}
