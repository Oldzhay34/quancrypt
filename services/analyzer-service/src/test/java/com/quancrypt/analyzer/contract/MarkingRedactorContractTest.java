package com.quancrypt.analyzer.contract;

import com.quancrypt.analyzer.fake.MarkingRedactor;
import com.quancrypt.analyzer.port.outbound.Redactor;

/** The test redactor keeps the port's contract, so the snippet tests built on it are meaningful. */
class MarkingRedactorContractTest extends RedactorContract {

    @Override
    protected Redactor redactor() {
        return new MarkingRedactor();
    }
}
