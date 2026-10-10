package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.contract.TopologyPortsContract;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the topology port contract, on PostgreSQL. */
class JdbcTopologyPortsContractTest extends TopologyPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
