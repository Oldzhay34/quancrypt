package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.PlanPortsContract;
import com.quancrypt.core.contract.PortSet;

/** The in-memory fakes against the plan port contract. */
class FakePlanPortsContractTest extends PlanPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
