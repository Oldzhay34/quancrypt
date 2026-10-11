package com.quancrypt.core.api.controller;

import com.quancrypt.core.facade.OutboxRelayFacade;
import com.quancrypt.core.facade.dto.RelayCountsDto;
import com.quancrypt.core.facade.dto.RelayRequestInput;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Endpoints for service to service calls only (X-Internal-Token); the security layer refuses the UI token with 403. */
@RestController
@RequestMapping("/api/v1/internal")
public class InternalController {

    private final OutboxRelayFacade relay;

    public InternalController(OutboxRelayFacade relay) {
        this.relay = relay;
    }

    @PostMapping("/outbox/relay")
    RelayCountsDto relay(@Valid @RequestBody RelayRequestInput body) {
        return relay.relayNow(body == null ? null : body.batchSize());
    }
}
