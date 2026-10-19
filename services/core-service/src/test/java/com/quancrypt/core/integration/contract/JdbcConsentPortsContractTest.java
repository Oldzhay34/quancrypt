package com.quancrypt.core.integration.contract;

import com.quancrypt.core.contract.ConsentPortsContract;
import com.quancrypt.core.contract.PortSet;
import com.quancrypt.core.integration.support.JdbcPortSet;

/** The JDBC adapters against the consent port contract, on PostgreSQL. */
class JdbcConsentPortsContractTest extends ConsentPortsContract {

    @Override
    protected PortSet newPorts() {
        return JdbcPortSet.fresh();
    }

    @Override
    protected int expectedLatestNoticeVersion() {
        return 2;
    }
}
