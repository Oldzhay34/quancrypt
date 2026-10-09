package com.quancrypt.core.fake;

import com.quancrypt.core.domain.model.ScanArtifact;
import com.quancrypt.core.port.outbound.ScanArtifactReader;
import com.quancrypt.core.port.outbound.ScanArtifactWriter;
import java.util.Optional;
import java.util.UUID;

/** CBOM files, one per scan. */
public final class FakeArtifacts implements ScanArtifactReader, ScanArtifactWriter {

    private final InMemoryDatabase db;

    public FakeArtifacts(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<ScanArtifact> find(UUID scanId) {
        return Optional.ofNullable(db.artifacts.get(scanId));
    }

    @Override
    public void save(ScanArtifact artifact) {
        db.artifacts.put(artifact.scanId(), artifact);
    }
}
