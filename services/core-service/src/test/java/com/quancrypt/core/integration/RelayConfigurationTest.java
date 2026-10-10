package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.quancrypt.core.CoreServiceApplication;
import com.quancrypt.core.api.scheduler.OutboxRelayScheduler;
import com.quancrypt.core.facade.OutboxRelayFacade;
import com.quancrypt.core.infrastructure.transaction.SpringTransactionRunner;
import com.quancrypt.core.integration.support.IngestApiStub;
import com.quancrypt.core.integration.support.PostgresTestDatabase;
import com.quancrypt.core.port.outbound.TransactionRunner;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

/**
 * The production composition root (no test doubles) under the three relay settings of D-155: off (the facade exists,
 * the trigger does not), on with INGEST_API_URL (the trigger exists), and on without it (the service refuses to start).
 */
class RelayConfigurationTest {

    private static final String SALT = "0123456789abcdef0123456789abcdef0123456789abcdef";
    private final IngestApiStub stub = new IngestApiStub();

    @AfterEach
    void stop() {
        stub.close();
    }

    private ConfigurableApplicationContext start(boolean relayEnabled, String ingestUrl) {
        PostgresTestDatabase database = PostgresTestDatabase.get();
        // Command-line arguments outrank application.yml, whose secrets have no default and would not resolve.
        return new SpringApplicationBuilder(CoreServiceApplication.class).run(
                "--spring.datasource.url=" + database.url(),
                "--spring.datasource.password=" + database.appPassword(),
                "--quancrypt.migration.password=" + database.migratorPassword(),
                "--quancrypt.anon-salt=" + SALT,
                "--quancrypt.outbox.ingest-url=" + ingestUrl,
                "--quancrypt.outbox.relay.enabled=" + relayEnabled,
                "--quancrypt.outbox.relay.interval=1m");
    }

    @Test
    void relayOffHasTheFacadeButNoTrigger() {
        try (ConfigurableApplicationContext context = start(false, "")) {
            assertThat(context.getBeansOfType(OutboxRelayScheduler.class)).isEmpty();
            assertThat(context.getBeansOfType(OutboxRelayFacade.class)).hasSize(1);
            assertThat(context.getBean(TransactionRunner.class)).isInstanceOf(SpringTransactionRunner.class);
        }
    }

    @Test
    void relayOnWithAnIngestUrlHasTheTrigger() {
        try (ConfigurableApplicationContext context = start(true, stub.url())) {
            assertThat(context.getBeansOfType(OutboxRelayScheduler.class)).hasSize(1);
            assertThat(context.getBeansOfType(OutboxRelayFacade.class)).hasSize(1);
        }
    }

    @Test
    void relayOnWithoutAnIngestUrlRefusesToStart() {
        Throwable failure = catchThrowable(() -> start(true, "").close());

        assertThat(failure).isNotNull();
        assertThat(failure).hasStackTraceContaining("OUTBOX_RELAY_ENABLED=true needs INGEST_API_URL");
    }
}
