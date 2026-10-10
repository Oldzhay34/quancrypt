package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.IdempotencyPortsContract;
import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the idempotency port contract, on PostgreSQL. */
class JdbcIdempotencyPortsContractTest extends IdempotencyPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
