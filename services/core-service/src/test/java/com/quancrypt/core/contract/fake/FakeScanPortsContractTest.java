package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.contract.ScanPortsContract;

/** The in-memory fakes against the scan port contract. */
class FakeScanPortsContractTest extends ScanPortsContract {

    @Override
    protected PortSet newPorts() {
        return PortSet.fake();
    }
}
