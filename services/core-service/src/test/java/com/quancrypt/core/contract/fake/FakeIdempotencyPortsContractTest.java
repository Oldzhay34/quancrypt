package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.IdempotencyPortsContract;
import com.quancrypt.core.contract.PortSet;

/** The in-memory fakes against the idempotency port contract. */
class FakeIdempotencyPortsContractTest extends IdempotencyPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
