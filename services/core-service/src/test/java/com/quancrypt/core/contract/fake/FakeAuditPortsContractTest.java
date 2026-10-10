package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.AuditPortsContract;
import com.quancrypt.core.contract.PortSet;

/** The in-memory fakes against the audit port contract. */
class FakeAuditPortsContractTest extends AuditPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
