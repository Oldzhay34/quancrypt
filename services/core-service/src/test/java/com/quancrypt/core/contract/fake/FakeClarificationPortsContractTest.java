package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.ClarificationPortsContract;
import com.quancrypt.core.contract.PortSet;

/** The in-memory fakes against the clarification port contract. */
class FakeClarificationPortsContractTest extends ClarificationPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
