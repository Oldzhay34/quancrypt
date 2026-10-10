package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.AuditPortsContract;
import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the audit port contract, on PostgreSQL. */
class JdbcAuditPortsContractTest extends AuditPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
