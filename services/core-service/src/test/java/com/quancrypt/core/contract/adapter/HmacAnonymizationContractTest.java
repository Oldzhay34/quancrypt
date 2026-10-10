package com.quancrypt.core.contract.adapter;

import com.quancrypt.core.contract.AnonymizationContract;
import com.quancrypt.core.infrastructure.anonymization.HmacEventAnonymizer;
import com.quancrypt.core.infrastructure.anonymization.RedactionRules;
import com.quancrypt.core.infrastructure.anonymization.Redactor;
import com.quancrypt.core.port.outbound.EventAnonymizer;
import com.quancrypt.core.port.outbound.ProjectKeyHasher;

/** HmacEventAnonymizer, with the packaged redaction rules, against the anonymization contract. */
class HmacAnonymizationContractTest extends AnonymizationContract {

    private final HmacEventAnonymizer adapter = new HmacEventAnonymizer("0123456789abcdef0123456789abcdef0123456789abcdef",
            new Redactor(RedactionRules.fromClasspath()));

    @Override
    protected ProjectKeyHasher hasher() {
        return adapter;
    }

    @Override
    protected EventAnonymizer anonymizer() {
        return adapter;
    }
}
