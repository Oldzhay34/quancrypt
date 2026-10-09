package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.AuditEntry;
import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.domain.model.ClarificationQuestion;
import com.quancrypt.core.domain.model.Consent;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.IdempotencyRecord;
import com.quancrypt.core.domain.model.OutboxRecord;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemTransition;
import com.quancrypt.core.domain.model.PrivacyNotice;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.RuntimeProfile;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.Topology;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** All tables of core_db in memory, with snapshots so a failed transaction can be rolled back in unit tests. */
public final class InMemoryDatabase {

    public final Map<UUID, Project> projects = new LinkedHashMap<>();
    public final Map<UUID, List<RuntimeProfile>> profiles = new HashMap<>();
    public final Map<UUID, Consent> consents = new LinkedHashMap<>();
    public final List<PrivacyNotice> notices = new ArrayList<>();
    public final Map<UUID, Scan> scans = new LinkedHashMap<>();
    public final Map<UUID, SourceFile> sourceFiles = new LinkedHashMap<>();
    public final Map<UUID, Finding> findings = new LinkedHashMap<>();
    public final Map<UUID, Topology> topologies = new LinkedHashMap<>();
    public final Map<UUID, ScanArtifact> artifacts = new LinkedHashMap<>();
    public final Map<UUID, Map<ClarificationQuestion, ClarificationAnswer>> answers = new HashMap<>();
    public final Map<UUID, Plan> plans = new LinkedHashMap<>();
    public final Map<UUID, PlanItem> planItems = new LinkedHashMap<>();
    public final List<PlanItemTransition> transitions = new ArrayList<>();
    public final List<AuditEntry> audit = new ArrayList<>();
    public final List<OutboxRecord> outbox = new ArrayList<>();
    public final Set<UUID> published = new HashSet<>();
    public final Map<String, IdempotencyRecord> idempotency = new LinkedHashMap<>();
    /** Row locks in the order they were taken; never rolled back, tests read it. */
    public final List<String> lockLog = new ArrayList<>();

    /** A deep-enough copy of every table. */
    public record Snapshot(
            Map<UUID, Project> projects, Map<UUID, List<RuntimeProfile>> profiles, Map<UUID, Consent> consents,
            List<PrivacyNotice> notices, Map<UUID, Scan> scans, Map<UUID, SourceFile> sourceFiles, Map<UUID, Finding> findings,
            Map<UUID, Topology> topologies, Map<UUID, ScanArtifact> artifacts,
            Map<UUID, Map<ClarificationQuestion, ClarificationAnswer>> answers, Map<UUID, Plan> plans,
            Map<UUID, PlanItem> planItems, List<PlanItemTransition> transitions, List<AuditEntry> audit,
            List<OutboxRecord> outbox, Set<UUID> published, Map<String, IdempotencyRecord> idempotency) {
    }

    public Snapshot snapshot() {
        Map<UUID, List<RuntimeProfile>> profileCopy = new HashMap<>();
        profiles.forEach((k, v) -> profileCopy.put(k, new ArrayList<>(v)));
        Map<UUID, Map<ClarificationQuestion, ClarificationAnswer>> answerCopy = new HashMap<>();
        answers.forEach((k, v) -> answerCopy.put(k, new HashMap<>(v)));
        return new Snapshot(new LinkedHashMap<>(projects), profileCopy, new LinkedHashMap<>(consents), new ArrayList<>(notices),
                new LinkedHashMap<>(scans), new LinkedHashMap<>(sourceFiles), new LinkedHashMap<>(findings),
                new LinkedHashMap<>(topologies), new LinkedHashMap<>(artifacts), answerCopy, new LinkedHashMap<>(plans),
                new LinkedHashMap<>(planItems), new ArrayList<>(transitions), new ArrayList<>(audit), new ArrayList<>(outbox),
                new HashSet<>(published), new LinkedHashMap<>(idempotency));
    }

    public void restore(Snapshot s) {
        replace(projects, s.projects());
        replace(profiles, s.profiles());
        replace(consents, s.consents());
        notices.clear();
        notices.addAll(s.notices());
        replace(scans, s.scans());
        replace(sourceFiles, s.sourceFiles());
        replace(findings, s.findings());
        replace(topologies, s.topologies());
        replace(artifacts, s.artifacts());
        replace(answers, s.answers());
        replace(plans, s.plans());
        replace(planItems, s.planItems());
        transitions.clear();
        transitions.addAll(s.transitions());
        audit.clear();
        audit.addAll(s.audit());
        outbox.clear();
        outbox.addAll(s.outbox());
        published.clear();
        published.addAll(s.published());
        replace(idempotency, s.idempotency());
    }

    private static <K, V> void replace(Map<K, V> target, Map<K, V> source) {
        target.clear();
        target.putAll(source);
    }

    /** The project a scan belongs to. */
    public UUID projectOf(UUID scanId) {
        return scans.get(scanId).projectId();
    }
}
