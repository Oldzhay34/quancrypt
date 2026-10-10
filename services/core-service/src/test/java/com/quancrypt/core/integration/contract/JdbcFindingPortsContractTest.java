package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.FindingPortsContract;
import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the finding port contract, on PostgreSQL. */
class JdbcFindingPortsContractTest extends FindingPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
