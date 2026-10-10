package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.contract.ScanPortsContract;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the scan port contract, on PostgreSQL. */
class JdbcScanPortsContractTest extends ScanPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
