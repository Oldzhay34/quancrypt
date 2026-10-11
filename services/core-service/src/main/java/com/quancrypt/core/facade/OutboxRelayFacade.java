package com.quancrypt.core.facade;

import com.quancrypt.core.facade.dto.RelayCountsDto;
import com.quancrypt.core.facade.dto.RelayOutcome;
import com.quancrypt.core.port.inbound.RelayOutboxEventsCommand;
import com.quancrypt.core.port.inbound.RelayOutboxEventsUseCase;
import com.quancrypt.core.port.inbound.view.RelayResult;

/** Entry point of the outbox relay for driving adapters (the scheduled trigger now, the internal REST endpoint in P2.4). */
public final class OutboxRelayFacade {

    public static final int DEFAULT_BATCH_SIZE = 100;

    private final RelayOutboxEventsUseCase relay;

    public OutboxRelayFacade(RelayOutboxEventsUseCase relay) {
        this.relay = relay;
    }

    public RelayOutcome relay(int batchSize) {
        RelayResult result = relay.execute(new RelayOutboxEventsCommand(batchSize));
        return new RelayOutcome(result.relayedCount(), result.remainingCount(), result.publishFailed());
    }

    /** The internal endpoint: an absent batchSize means the default of 100; use case failures become ApiProblemException. */
    public RelayCountsDto relayNow(Integer batchSize) {
        RelayResult result = ProblemTranslator.call(() -> relay.execute(new RelayOutboxEventsCommand(batchSize == null ? DEFAULT_BATCH_SIZE : batchSize)));
        return new RelayCountsDto(result.relayedCount(), result.remainingCount());
    }
}
