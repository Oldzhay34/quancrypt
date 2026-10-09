package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.ProjectKey;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.ProjectReader;
import com.quancrypt.core.port.outbound.ProjectWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Projects, their reads, writes and row locks. */
public final class FakeProjects implements ProjectReader, ProjectWriter, ProjectLock {

    private final InMemoryDatabase db;

    public FakeProjects(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<Project> findById(UUID projectId) {
        return Optional.ofNullable(db.projects.get(projectId));
    }

    @Override
    public Optional<Project> findByKey(ProjectKey key) {
        return db.projects.values().stream().filter(p -> p.key().equals(key)).findFirst();
    }

    @Override
    public PageResult<Project> page(int page, int size) {
        List<Project> all = new ArrayList<>(db.projects.values());
        Collections.reverse(all);
        return FakePaging.slice(all, page, size);
    }

    @Override
    public boolean insertIfAbsent(Project project) {
        if (findByKey(project.key()).isPresent()) {
            return false;
        }
        db.projects.put(project.id(), project);
        return true;
    }

    @Override
    public void delete(UUID projectId) {
        db.projects.remove(projectId);
        db.profiles.remove(projectId);
        db.answers.remove(projectId);
        db.consents.values().removeIf(c -> c.projectId().equals(projectId));
        Set<UUID> scanIds = db.scans.values().stream().filter(s -> s.projectId().equals(projectId)).map(Scan::id).collect(Collectors.toSet());
        Set<UUID> fileIds = db.sourceFiles.values().stream().filter(f -> scanIds.contains(f.scanId())).map(SourceFile::id).collect(Collectors.toSet());
        Set<UUID> planIds = db.plans.values().stream().filter(p -> scanIds.contains(p.scanId())).map(Plan::id).collect(Collectors.toSet());
        Set<UUID> itemIds = db.planItems.values().stream().filter(i -> planIds.contains(i.planId())).map(PlanItem::id).collect(Collectors.toSet());
        db.transitions.removeIf(t -> itemIds.contains(t.planItemId()));
        db.planItems.keySet().removeAll(itemIds);
        db.plans.keySet().removeAll(planIds);
        db.findings.values().removeIf(f -> fileIds.contains(f.sourceFileId()));
        db.sourceFiles.keySet().removeAll(fileIds);
        db.topologies.keySet().removeAll(scanIds);
        db.artifacts.keySet().removeAll(scanIds);
        db.scans.keySet().removeAll(scanIds);
    }

    @Override
    public Optional<Project> keyShare(UUID projectId) {
        db.lockLog.add("project:keyShare");
        return findById(projectId);
    }

    @Override
    public Optional<Project> noKeyUpdate(UUID projectId) {
        db.lockLog.add("project:noKeyUpdate");
        return findById(projectId);
    }

    @Override
    public Optional<Project> update(UUID projectId) {
        db.lockLog.add("project:update");
        return findById(projectId);
    }
}
