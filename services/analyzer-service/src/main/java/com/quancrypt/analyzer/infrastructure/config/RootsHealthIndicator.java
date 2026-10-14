package com.quancrypt.analyzer.infrastructure.config;

import com.quancrypt.analyzer.domain.model.AllowedRoots;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

/**
 * Readiness: the service can analyze when at least one directory it may read exists, that is when a project is mounted
 * (docker-local: {@code ${PROJECT_ROOT}:/workspace:ro}). The canonical dictionary and the redaction rules are loaded
 * while the context starts, so a missing one stops the service before it can report anything.
 */
@Component("analyzerHealthIndicator")
public class RootsHealthIndicator implements HealthIndicator {

    private final AllowedRoots allowedRoots;

    public RootsHealthIndicator(AllowedRoots allowedRoots) {
        this.allowedRoots = allowedRoots;
    }

    @Override
    public Health health() {
        boolean mounted = allowedRoots.directories().stream().anyMatch(directory -> Files.isDirectory(Path.of(directory)));
        return mounted ? Health.up().build() : Health.down().build();
    }
}
