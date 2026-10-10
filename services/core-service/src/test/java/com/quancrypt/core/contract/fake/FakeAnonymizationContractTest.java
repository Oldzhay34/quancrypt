package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.AnonymizationContract;
import com.quancrypt.core.fake.PassThroughAnonymizer;
import com.quancrypt.core.fake.Sha256ProjectKeyHasher;
import com.quancrypt.core.port.outbound.EventAnonymizer;
import com.quancrypt.core.port.outbound.ProjectKeyHasher;

/** The unsalted hasher and pass-through anonymizer fakes against the anonymization contract. */
class FakeAnonymizationContractTest extends AnonymizationContract {

    @Override
    protected ProjectKeyHasher hasher() {
        return new Sha256ProjectKeyHasher();
    }

    @Override
    protected EventAnonymizer anonymizer() {
        return new PassThroughAnonymizer();
    }
}
