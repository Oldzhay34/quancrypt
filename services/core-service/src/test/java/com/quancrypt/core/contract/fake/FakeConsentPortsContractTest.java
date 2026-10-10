package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.ConsentPortsContract;
import com.quancrypt.core.contract.PortSet;

/** The in-memory fakes against the consent port contract. */
class FakeConsentPortsContractTest extends ConsentPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
