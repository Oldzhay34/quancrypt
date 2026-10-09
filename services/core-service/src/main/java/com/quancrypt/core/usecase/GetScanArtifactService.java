package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.port.inbound.GetScanArtifactQuery;
import com.quancrypt.core.port.inbound.GetScanArtifactUseCase;
import com.quancrypt.core.port.inbound.view.ScanArtifactContentView;
import com.quancrypt.core.port.outbound.ScanArtifactReader;

/** Reads the CBOM file of a scan. */
public final class GetScanArtifactService implements GetScanArtifactUseCase {

    private final ScanArtifactReader artifacts;

    public GetScanArtifactService(ScanArtifactReader artifacts) {
        this.artifacts = artifacts;
    }

    @Override
    public ScanArtifactContentView execute(GetScanArtifactQuery input) {
        ScanArtifact artifact = artifacts.find(input.scanId()).orElseThrow(() -> Fail.notFound("scan artifact"));
        return new ScanArtifactContentView(artifact.contentType(), artifact.sha256(), artifact.content());
    }
}
