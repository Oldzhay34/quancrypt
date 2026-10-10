package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.ClarificationPortsContract;
import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the clarification port contract, on PostgreSQL. */
class JdbcClarificationPortsContractTest extends ClarificationPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
