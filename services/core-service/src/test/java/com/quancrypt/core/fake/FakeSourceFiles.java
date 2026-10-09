package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.Topology;
import com.quancrypt.core.port.outbound.SourceFileReader;
import com.quancrypt.core.port.outbound.SourceFileWriter;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Source files of scans. */
public final class FakeSourceFiles implements SourceFileReader, SourceFileWriter {

    private final InMemoryDatabase db;

    public FakeSourceFiles(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Map<String, SourceFile> byPaths(UUID scanId, Collection<String> paths) {
        return db.sourceFiles.values().stream()
                .filter(f -> f.scanId().equals(scanId) && paths.contains(f.path()))
                .collect(Collectors.toMap(SourceFile::path, f -> f));
    }

    @Override
    public Optional<SourceFile> find(UUID sourceFileId) {
        return Optional.ofNullable(db.sourceFiles.get(sourceFileId));
    }

    @Override
    public Map<UUID, SourceFile> byIds(Collection<UUID> sourceFileIds) {
        return sourceFileIds.stream().map(db.sourceFiles::get).filter(Objects::nonNull).collect(Collectors.toMap(SourceFile::id, f -> f));
    }

    @Override
    public void insertAll(List<SourceFile> files) {
        for (SourceFile file : files) {
            boolean duplicate = db.sourceFiles.values().stream().anyMatch(f -> f.scanId().equals(file.scanId()) && f.path().equals(file.path()));
            if (duplicate) {
                throw new IllegalStateException("duplicate source file " + file.path());
            }
            db.sourceFiles.put(file.id(), file);
        }
    }

    @Override
    public int deleteUnreferenced(UUID scanId) {
        Set<UUID> referenced = new HashSet<>();
        db.findings.values().forEach(f -> referenced.add(f.sourceFileId()));
        Topology topology = db.topologies.get(scanId);
        if (topology != null) {
            topology.links().forEach(l -> l.callSites().forEach(cs -> referenced.add(cs.sourceFileId())));
        }
        List<UUID> doomed = db.sourceFiles.values().stream()
                .filter(f -> f.scanId().equals(scanId) && !referenced.contains(f.id())).map(SourceFile::id).toList();
        doomed.forEach(db.sourceFiles::remove);
        return doomed.size();
    }
}
