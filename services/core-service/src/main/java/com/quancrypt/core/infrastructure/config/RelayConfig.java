package com.quancrypt.core.infrastructure.config;

import com.quancrypt.core.api.scheduler.OutboxRelayScheduler;
import com.quancrypt.core.facade.OutboxRelayFacade;
import java.time.Clock;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * The scheduled outbox relay trigger; it exists only with OUTBOX_RELAY_ENABLED=true (D-155). Until ingest-api arrives
 * (P6.1) the trigger stays off and events accumulate in the outbox. The facade itself is always present (FacadeConfig).
 */
@Configuration(proxyBeanMethods = false)
@EnableScheduling
@ConditionalOnProperty(name = "quancrypt.outbox.relay.enabled", havingValue = "true")
public class RelayConfig {

    @Bean
    OutboxRelayScheduler outboxRelayScheduler(
            OutboxRelayFacade facade,
            @Value("${quancrypt.outbox.relay.batch-size:100}") int batchSize,
            @Value("${quancrypt.outbox.relay.interval:5s}") Duration interval,
            @Value("${quancrypt.outbox.relay.max-backoff:5m}") Duration maxBackoff) {
        return new OutboxRelayScheduler(facade, batchSize, interval, maxBackoff, Clock.systemUTC());
    }
}
