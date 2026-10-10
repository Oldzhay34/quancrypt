package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.contract.TopologyPortsContract;

/** The in-memory fakes against the topology port contract. */
class FakeTopologyPortsContractTest extends TopologyPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
