package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.FindingPortsContract;
import com.quancrypt.core.contract.PortSet;

/** The in-memory fakes against the finding port contract. */
class FakeFindingPortsContractTest extends FindingPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
