package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.FindingView;

/** Reads one finding. */
public interface GetFindingUseCase {

    FindingView execute(GetFindingQuery input);
}
