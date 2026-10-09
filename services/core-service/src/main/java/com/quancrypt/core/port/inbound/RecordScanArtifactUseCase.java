package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.ScanArtifactView;

/** Stores the CBOM file of a running scan. */
public interface RecordScanArtifactUseCase {

    ScanArtifactView execute(RecordScanArtifactCommand input);
}
