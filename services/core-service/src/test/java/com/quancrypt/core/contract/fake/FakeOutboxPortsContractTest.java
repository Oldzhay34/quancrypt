package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.OutboxPortsContract;
import com.quancrypt.core.contract.PortSet;

/** The in-memory fakes against the outbox port contract. */
class FakeOutboxPortsContractTest extends OutboxPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
