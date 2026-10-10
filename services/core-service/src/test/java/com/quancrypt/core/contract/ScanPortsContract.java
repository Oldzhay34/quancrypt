package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.core.domain.exception.ScanAlreadyRunningException;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.domain.model.ScanStatus;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** ScanReader, ScanWriter, ScanLock and the CBOM artifact ports. */
public abstract class ScanPortsContract extends PortContract {

    @Test
    void oneRunningScanPerProject() {
        Project project = project("Demo", T0);
        Scan scan = runningScan(project.id(), at(1));

        assertThatThrownBy(() -> runningScan(project.id(), at(2))).isInstanceOf(ScanAlreadyRunningException.class);
        assertThat(ports.scanReader().find(scan.id())).contains(scan);
        assertThat(ports.scanReader().projectIdOf(scan.id())).contains(project.id());
        assertThat(ports.scanLock().noKeyUpdate(scan.id())).contains(scan);
        assertThat(ports.scanLock().share(scan.id())).contains(scan);
        assertThat(ports.scanLock().share(UUID.randomUUID())).isEmpty();
    }

    @Test
    void finishIfRunningFinishesOnce() {
        Project project = project("Demo", T0);
        Scan scan = runningScan(project.id(), at(1));

        assertThat(ports.scanWriter().finishIfRunning(scan.id(), ScanStatus.COMPLETED, at(5))).isTrue();
        assertThat(ports.scanWriter().finishIfRunning(scan.id(), ScanStatus.FAILED, at(6))).isFalse();
        assertThat(ports.scanReader().find(scan.id())).contains(scan.finish(ScanStatus.COMPLETED, at(5)));
        runningScan(project.id(), at(7));
    }

    @Test
    void scansOfAProjectArePagedNewestFirst() {
        Project project = project("Demo", T0);
        Scan first = runningScan(project.id(), at(1));
        ports.scanWriter().finishIfRunning(first.id(), ScanStatus.COMPLETED, at(2));
        Scan second = runningScan(project.id(), at(3));

        assertThat(ports.scanReader().pageByProject(project.id(), 0, 10).items())
                .extracting(Scan::id).containsExactly(second.id(), first.id());
        assertThat(ports.scanReader().pageByProject(project.id(), 0, 1).total()).isEqualTo(2);
    }

    @Test
    void artifactIsStoredAndReplaced() {
        Tree tree = tree();
        ScanArtifact first = ScanArtifact.of(tree.scan().id(), "application/vnd.cyclonedx+json", "{\"a\":1}".getBytes(StandardCharsets.UTF_8), at(2));
        ScanArtifact second = ScanArtifact.of(tree.scan().id(), "application/json", "{\"b\":2}".getBytes(StandardCharsets.UTF_8), at(3));

        ports.artifactWriter().save(first);
        ports.artifactWriter().save(second);

        ScanArtifact stored = ports.artifactReader().find(tree.scan().id()).orElseThrow();
        assertThat(stored.content()).isEqualTo(second.content());
        assertThat(stored.sha256()).isEqualTo(second.sha256());
        assertThat(stored.contentType()).isEqualTo("application/json");
        assertThat(stored.createdAt()).isEqualTo(at(3));
        assertThat(ports.artifactReader().find(UUID.randomUUID())).isEmpty();
    }
}
