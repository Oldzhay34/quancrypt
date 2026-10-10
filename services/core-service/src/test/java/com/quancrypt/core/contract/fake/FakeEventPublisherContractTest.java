package com.quancrypt.core.contract.fake;

import com.quancrypt.core.contract.EventPublisherContract;
import com.quancrypt.core.fake.RecordingPublisher;
import com.quancrypt.core.port.outbound.EventPublisher;

/** The recording fake publisher against the EventPublisher contract. */
class FakeEventPublisherContractTest extends EventPublisherContract {

    @Override
    protected EventPublisher accepting() {
        return new RecordingPublisher();
    }

    @Override
    protected EventPublisher failing() {
        RecordingPublisher publisher = new RecordingPublisher();
        publisher.failing(true);
        return publisher;
    }
}
