package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.contract.ProjectPortsContract;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the project port contract, on PostgreSQL. */
class JdbcProjectPortsContractTest extends ProjectPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
