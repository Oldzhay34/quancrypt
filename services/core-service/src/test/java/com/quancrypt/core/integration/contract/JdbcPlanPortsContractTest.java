package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.PlanPortsContract;
import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the plan port contract, on PostgreSQL. */
class JdbcPlanPortsContractTest extends PlanPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }
}
