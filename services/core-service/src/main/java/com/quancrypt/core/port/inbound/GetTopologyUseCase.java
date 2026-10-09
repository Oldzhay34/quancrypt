package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.TopologyView;

/** Reads the topology of a scan. */
public interface GetTopologyUseCase {

    TopologyView execute(GetTopologyQuery input);
}
