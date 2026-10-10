package com.quancrypt.core.integration.support;

import com.quancrypt.core.infrastructure.persistence.FlywayMigrator;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.List;
import java.util.stream.Stream;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.utility.MountableFile;

/**
 * One PostgreSQL container for every integration test: the image of VERSIONS.md and the repository's own init scripts
 * (infra/postgres/init), so roles, databases and default privileges are exactly those of `make up` (D-54, D-59).
 * Role passwords are random per run; .env is never read (D-55). The migrations run once, as core_db_migrator.
 */
public final class PostgresTestDatabase {

    public static final String IMAGE = "pgvector/pgvector:0.8.7-pg16";
    private static final List<String> ROLE_PASSWORDS = List.of(
            "POSTGRES_PASSWORD", "CORE_DB_MIGRATOR_PASSWORD", "CORE_DB_APP_PASSWORD", "AGENT_DB_MIGRATOR_PASSWORD",
            "AGENT_DB_APP_PASSWORD", "WAREHOUSE_DB_MIGRATOR_PASSWORD", "WAREHOUSE_DB_APP_PASSWORD", "WAREHOUSE_READER_PASSWORD",
            "MLFLOW_DB_MIGRATOR_PASSWORD", "MLFLOW_DB_APP_PASSWORD");

    private static final SecureRandom RANDOM = new SecureRandom();
    private static final PostgresTestDatabase INSTANCE = new PostgresTestDatabase();

    private final GenericContainer<?> container;
    private final String appPassword;
    private final String migratorPassword;
    private final HikariDataSource app;
    private final HikariDataSource migrator;

    @SuppressWarnings("resource")
    private PostgresTestDatabase() {
        container = new GenericContainer<>(IMAGE).withExposedPorts(5432)
                .waitingFor(Wait.forLogMessage(".*database system is ready to accept connections.*\\s", 2));
        for (String name : ROLE_PASSWORDS) {
            container.withEnv(name, randomSecret());
        }
        try (Stream<Path> scripts = Files.list(Path.of(System.getProperty("quancrypt.infra.dir"), "postgres", "init"))) {
            scripts.filter(p -> p.toString().endsWith(".sh")).sorted().forEach(p ->
                    container.withCopyFileToContainer(MountableFile.forHostPath(p, 0755), "/docker-entrypoint-initdb.d/" + p.getFileName()));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        container.start();
        appPassword = container.getEnvMap().get("CORE_DB_APP_PASSWORD");
        migratorPassword = container.getEnvMap().get("CORE_DB_MIGRATOR_PASSWORD");
        new FlywayMigrator(url(), "core_db_migrator", migratorPassword).migrate();
        app = pool("core_db_app", appPassword, 12);
        migrator = pool("core_db_migrator", migratorPassword, 2);
    }

    public static PostgresTestDatabase get() {
        return INSTANCE;
    }

    private static String randomSecret() {
        byte[] bytes = new byte[24];
        RANDOM.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    private HikariDataSource pool(String user, String password, int size) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(url());
        config.setUsername(user);
        config.setPassword(password);
        config.setMaximumPoolSize(size);
        return new HikariDataSource(config);
    }

    public String url() {
        return "jdbc:postgresql://" + container.getHost() + ":" + container.getMappedPort(5432) + "/core_db";
    }

    public String appPassword() {
        return appPassword;
    }

    public String migratorPassword() {
        return migratorPassword;
    }

    /** Connections as core_db_app, the role the service uses. */
    public DataSource app() {
        return app;
    }

    /** Connections as core_db_migrator (schema owner); tests use it only for clean-up and catalog checks. */
    public DataSource migrator() {
        return migrator;
    }

    /** Empties every table except the lookups and the seeded privacy notice; cascades through the project tree. */
    public void truncate() {
        JdbcClient.create(migrator).sql("TRUNCATE project, audit_log, outbox_event, idempotency_record CASCADE").update();
    }
}
