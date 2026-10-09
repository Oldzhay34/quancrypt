package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ScanArtifactContentView;

/** Reads the CBOM file of a scan. */
public interface GetScanArtifactUseCase {

    ScanArtifactContentView execute(GetScanArtifactQuery input);
}
