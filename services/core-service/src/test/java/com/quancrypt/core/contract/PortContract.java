package com.quancrypt.core.contract;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.infrastructure.id.RandomIdGenerator;
import com.quancrypt.core.port.outbound.IdGenerator;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;

/**
 * Base of the outbound port contract tests (LSP, solid-checklist): the in-memory fakes of the unit tests and the JDBC
 * adapters run the same assertions. Subclasses only say which implementation family to use.
 */
public abstract class PortContract {

    protected static final Instant T0 = Instant.parse("2026-10-09T10:00:00Z");
    private static final SecureRandom RANDOM = new SecureRandom();

    protected final IdGenerator ids = new RandomIdGenerator();
    protected PortSet ports;

    protected abstract PortSet newPorts();

    @BeforeEach
    void createPorts() {
        ports = newPorts();
    }

    protected static Instant at(int seconds) {
        return T0.plus(Duration.ofSeconds(seconds));
    }

    protected static ProjectKey randomKey() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return new ProjectKey(HexFormat.of().formatHex(bytes));
    }

    protected Project project(String name, Instant createdAt) {
        Project project = new Project(ids.next(), randomKey(), name, createdAt);
        ports.projectWriter().insertIfAbsent(project);
        return project;
    }

    protected Scan runningScan(UUID projectId, Instant startedAt) {
        Scan scan = Scan.start(ids.next(), projectId, Optional.empty(), startedAt);
        ports.scanWriter().insertRunning(scan);
        return scan;
    }

    protected SourceFile file(UUID scanId, String path, LocationKind kind) {
        SourceFile file = new SourceFile(ids.next(), scanId, path, kind);
        ports.sourceFileWriter().insertAll(List.of(file));
        return file;
    }

    protected Finding finding(UUID fileId, String symbol, Priority priority, Integer line) {
        return new Finding(ids.next(), fileId, symbol, AlgorithmFamily.RSA, UsageContext.TLS_KEY_EXCHANGE, priority, Optional.of(2048),
                Optional.ofNullable(line), Optional.ofNullable(line), 0.9, ClassifiedBy.STATIC);
    }

    /** A project with one running scan and one source file; the usual starting point below the scan. */
    protected record Tree(Project project, Scan scan, SourceFile file) {
    }

    protected Tree tree() {
        Project project = project("Demo", T0);
        Scan scan = runningScan(project.id(), at(1));
        return new Tree(project, scan, file(scan.id(), "src/main/java/Tls.java", LocationKind.CODE));
    }
}
