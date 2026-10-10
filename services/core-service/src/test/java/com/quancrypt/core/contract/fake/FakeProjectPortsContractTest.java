package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.contract.ProjectPortsContract;

/** The in-memory fakes against the project port contract. */
class FakeProjectPortsContractTest extends ProjectPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
