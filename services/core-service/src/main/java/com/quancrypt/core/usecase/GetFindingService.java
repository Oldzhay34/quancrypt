package com.quancrypt.core.usecase;

import com.quancrypt.core.port.inbound.GetFindingQuery;
import com.quancrypt.core.port.inbound.GetFindingUseCase;
import com.quancrypt.core.port.inbound.view.FindingView;
import com.quancrypt.core.port.outbound.FindingReader;

/** Reads one finding with its evidence. */
public final class GetFindingService implements GetFindingUseCase {

    private final FindingReader findings;

    public GetFindingService(FindingReader findings) {
        this.findings = findings;
    }

    @Override
    public FindingView execute(GetFindingQuery input) {
        return findings.find(input.findingId()).map(ViewMapper::finding).orElseThrow(() -> Fail.notFound("finding"));
    }
}
