package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.TopologyView;

/** Records the topology of a running scan. */
public interface RecordTopologyUseCase {

    TopologyView execute(RecordTopologyCommand input);
}
