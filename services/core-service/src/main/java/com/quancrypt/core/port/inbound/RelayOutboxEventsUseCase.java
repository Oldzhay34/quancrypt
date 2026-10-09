package com.quancrypt.core.port.inbound;

import com.quancrypt.core.port.inbound.view.RelayResult;

/** Relays pending outbox events. */
public interface RelayOutboxEventsUseCase {

    RelayResult execute(RelayOutboxEventsCommand input);
}
