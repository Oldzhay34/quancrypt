package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ScanView;

/** Starts a scan; one running scan per project. */
public interface StartScanUseCase {

    ScanView execute(StartScanCommand input);
}
