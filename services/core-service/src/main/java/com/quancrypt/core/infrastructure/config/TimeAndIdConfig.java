package com.quancrypt.core.infrastructure.config;

import com.quancrypt.core.infrastructure.id.RandomIdGenerator;
import com.quancrypt.core.infrastructure.time.SystemClock;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IdGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** The clock and id generator every use case and adapter shares. */
@Configuration(proxyBeanMethods = false)
public class TimeAndIdConfig {

    @Bean
    Clock clock() {
        return new SystemClock(java.time.Clock.systemUTC());
    }

    @Bean
    IdGenerator idGenerator() {
        return new RandomIdGenerator();
    }
}
