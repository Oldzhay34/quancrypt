package com.quancrypt.core.infrastructure.persistence;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.output.MigrateResult;

/**
 * Applies the core_db migrations as core_db_migrator, the owner of the schema (D-54); the service itself connects as
 * core_db_app, which only has DML rights through the default privileges the init script grants.
 */
public final class FlywayMigrator {

    public static final String LOCATION = "classpath:db/migration";

    private final String url;
    private final String user;
    private final String password;

    public FlywayMigrator(String url, String user, String password) {
        this.url = url;
        this.user = user;
        this.password = password;
    }

    public MigrateResult migrate() {
        return Flyway.configure()
                .dataSource(url, user, password)
                .locations(LOCATION)
                .cleanDisabled(true)
                .load()
                .migrate();
    }
}
