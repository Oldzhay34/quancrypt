package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.OutboxPortsContract;
import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the outbox port contract, on PostgreSQL. */
class JdbcOutboxPortsContractTest extends OutboxPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
