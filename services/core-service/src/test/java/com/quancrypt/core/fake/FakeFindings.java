package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.FindingDetail;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.ServiceLink;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.port.outbound.FindingContext;
import com.quancrypt.core.port.outbound.FindingFilter;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.FindingStats;
import com.quancrypt.core.port.outbound.FindingWriter;
import com.quancrypt.core.port.outbound.PlanningContextReader;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/** Findings, their file join, statistics and the topology-derived planning context. */
public final class FakeFindings implements FindingReader, FindingWriter, PlanningContextReader {

    private final InMemoryDatabase db;

    public FakeFindings(InMemoryDatabase db) {
        this.db = db;
    }

    private FindingDetail detail(Finding finding) {
        return new FindingDetail(finding, db.sourceFiles.get(finding.sourceFileId()));
    }

    private List<FindingDetail> ofScan(UUID scanId) {
        return db.findings.values().stream()
                .filter(f -> db.sourceFiles.get(f.sourceFileId()).scanId().equals(scanId))
                .map(this::detail).toList();
    }

    @Override
    public Optional<FindingDetail> find(UUID findingId) {
        return Optional.ofNullable(db.findings.get(findingId)).map(this::detail);
    }

    @Override
    public PageResult<FindingDetail> page(UUID scanId, FindingFilter filter, int page, int size) {
        List<FindingDetail> matching = ofScan(scanId).stream()
                .filter(d -> filter.priority().map(p -> p == d.finding().priority()).orElse(true))
                .filter(d -> filter.algorithmFamily().map(a -> a == d.finding().algorithm()).orElse(true))
                .filter(d -> filter.usageContext().map(u -> u == d.finding().usage()).orElse(true))
                .filter(d -> filter.locationKind().map(k -> k == d.file().locationKind()).orElse(true))
                .filter(d -> filter.classifiedBy().map(c -> c == d.finding().classifiedBy()).orElse(true))
                .toList();
        return FakePaging.slice(matching, page, size);
    }

    @Override
    public int countByScan(UUID scanId) {
        return ofScan(scanId).size();
    }

    @Override
    public List<FindingDetail> listByScan(UUID scanId) {
        return ofScan(scanId);
    }

    @Override
    public FindingStats stats(UUID scanId) {
        List<FindingDetail> all = ofScan(scanId);
        Map<Priority, Integer> byPriority = new EnumMap<>(Priority.class);
        Map<AlgorithmFamily, Integer> byAlgorithm = new EnumMap<>(AlgorithmFamily.class);
        Map<LocationKind, Integer> byKind = new EnumMap<>(LocationKind.class);
        for (FindingDetail d : all) {
            byPriority.merge(d.finding().priority(), 1, Integer::sum);
            byAlgorithm.merge(d.finding().algorithm(), 1, Integer::sum);
            byKind.merge(d.file().locationKind(), 1, Integer::sum);
        }
        return new FindingStats(all.size(), byPriority, byAlgorithm, byKind);
    }

    @Override
    public List<UUID> insertIgnoringDuplicates(List<Finding> findings) {
        List<UUID> inserted = new ArrayList<>();
        for (Finding finding : findings) {
            boolean exists = db.findings.values().stream().anyMatch(f -> sameLocation(f, finding));
            if (!exists) {
                db.findings.put(finding.id(), finding);
                inserted.add(finding.id());
            }
        }
        return inserted;
    }

    private static boolean sameLocation(Finding a, Finding b) {
        return a.sourceFileId().equals(b.sourceFileId()) && a.symbol().equals(b.symbol()) && a.algorithm() == b.algorithm()
                && a.usage() == b.usage() && a.lineStart().equals(b.lineStart());
    }

    @Override
    public Map<UUID, FindingContext> load(UUID scanId) {
        Topology topology = db.topologies.get(scanId);
        Map<UUID, FindingContext> context = new HashMap<>();
        for (FindingDetail d : ofScan(scanId)) {
            boolean device = false;
            int callSites = 0;
            if (topology != null) {
                for (ServiceLink link : topology.links()) {
                    if (link.findingIds().contains(d.finding().id())) {
                        device |= topology.isDeviceLink(link);
                        callSites += link.callSites().size();
                    }
                }
            }
            context.put(d.finding().id(), new FindingContext(device, callSites));
        }
        return context;
    }
}
