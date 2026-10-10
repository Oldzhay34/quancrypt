package com.quancrypt.core.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.model.Scan;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** ProjectReader, ProjectWriter, ProjectLock and the runtime profile ports. */
public abstract class ProjectPortsContract extends PortContract {

    @Test
    void insertIfAbsentInsertsOnceAndFindsByIdAndKey() {
        Project project = project("Demo", T0);
        Project sameKey = new Project(ids.next(), project.key(), "Other", at(5));

        assertThat(ports.projectWriter().insertIfAbsent(sameKey)).isFalse();
        assertThat(ports.projectReader().findById(project.id())).contains(project);
        assertThat(ports.projectReader().findByKey(project.key())).contains(project);
        assertThat(ports.projectReader().findById(sameKey.id())).isEmpty();
    }

    @Test
    void pageListsNewestFirstWithTotal() {
        Project first = project("First", at(1));
        Project second = project("Second", at(2));
        Project third = project("Third", at(3));

        PageResult<Project> page0 = ports.projectReader().page(0, 2);
        PageResult<Project> page1 = ports.projectReader().page(1, 2);

        assertThat(page0.items()).containsExactly(third, second);
        assertThat(page1.items()).containsExactly(first);
        assertThat(page0.total()).isEqualTo(3);
    }

    @Test
    void locksReturnTheProjectOrNothing() {
        Project project = project("Demo", T0);

        assertThat(ports.projectLock().keyShare(project.id())).contains(project);
        assertThat(ports.projectLock().noKeyUpdate(project.id())).contains(project);
        assertThat(ports.projectLock().update(project.id())).contains(project);
        assertThat(ports.projectLock().keyShare(UUID.randomUUID())).isEmpty();
    }

    @Test
    void deleteRemovesTheProjectAndEverythingBelowIt() {
        Project project = project("Demo", T0);
        Scan scan = runningScan(project.id(), at(1));
        ports.profileWriter().insert(project.id(), new RuntimeProfile(1, "21", Optional.empty(), at(2)));

        ports.projectWriter().delete(project.id());

        assertThat(ports.projectReader().findById(project.id())).isEmpty();
        assertThat(ports.scanReader().find(scan.id())).isEmpty();
        assertThat(ports.profileReader().current(project.id())).isEmpty();
    }

    @Test
    void currentProfileIsTheHighestSequence() {
        Project project = project("Demo", T0);
        RuntimeProfile first = new RuntimeProfile(1, "17", Optional.of("3.2.0"), at(1));
        RuntimeProfile second = new RuntimeProfile(2, "21", Optional.empty(), at(2));
        ports.profileWriter().insert(project.id(), first);
        ports.profileWriter().insert(project.id(), second);

        assertThat(ports.profileReader().current(project.id())).contains(second);
        assertThat(ports.profileReader().bySequence(project.id(), 1)).contains(first);
        assertThat(ports.profileReader().bySequence(project.id(), 3)).isEmpty();
    }
}
