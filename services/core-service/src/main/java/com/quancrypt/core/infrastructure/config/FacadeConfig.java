package com.quancrypt.core.infrastructure.config;

import com.quancrypt.core.facade.OutboxRelayFacade;
import com.quancrypt.core.port.inbound.RelayOutboxEventsUseCase;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** The facades the driving adapters use; present whether or not the relay trigger is enabled. */
@Configuration(proxyBeanMethods = false)
public class FacadeConfig {

    @Bean
    OutboxRelayFacade outboxRelayFacade(RelayOutboxEventsUseCase relay) {
        return new OutboxRelayFacade(relay);
    }
}
