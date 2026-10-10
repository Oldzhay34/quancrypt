package com.quancrypt.core.facade;

import com.quancrypt.core.facade.dto.RelayOutcome;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsUseCase;
import com.quancrypt.core.port.inbound.view.RelayResult;

/** Entry point of the outbox relay for driving adapters (the scheduled trigger now, the internal REST endpoint in P2.4). */
public final class OutboxRelayFacade {

    private final RelayOutboxEventsUseCase relay;

    public OutboxRelayFacade(RelayOutboxEventsUseCase relay) {
        this.relay = relay;
    }

    public RelayOutcome relay(int batchSize) {
        RelayResult result = relay.execute(new RelayOutboxEventsCommand(batchSize));
        return new RelayOutcome(result.relayedCount(), result.remainingCount(), result.publishFailed());
    }
}
