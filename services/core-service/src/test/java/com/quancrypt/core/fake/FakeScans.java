package com.quancrypt.core.fake;

import com.quancrypt.core.domain.exception.ScanAlreadyRunningException;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanStatus;
import com.quancrypt.core.port.outbound.ScanLock;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.ScanWriter;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Scans with locks and the one-running-scan-per-project rule. */
public final class FakeScans implements ScanReader, ScanLock, ScanWriter {

    private final InMemoryDatabase db;

    public FakeScans(InMemoryDatabase db) {
        this.db = db;
    }

    @Override
    public Optional<Scan> find(UUID scanId) {
        return Optional.ofNullable(db.scans.get(scanId));
    }

    @Override
    public Optional<UUID> projectIdOf(UUID scanId) {
        return find(scanId).map(Scan::projectId);
    }

    @Override
    public PageResult<Scan> pageByProject(UUID projectId, int page, int size) {
        List<Scan> all = new ArrayList<>(db.scans.values().stream().filter(s -> s.projectId().equals(projectId)).toList());
        Collections.reverse(all);
        return FakePaging.slice(all, page, size);
    }

    @Override
    public Optional<Scan> noKeyUpdate(UUID scanId) {
        db.lockLog.add("scan:noKeyUpdate");
        return find(scanId);
    }

    @Override
    public Optional<Scan> share(UUID scanId) {
        db.lockLog.add("scan:share");
        return find(scanId);
    }

    @Override
    public void insertRunning(Scan scan) {
        boolean running = db.scans.values().stream().anyMatch(s -> s.projectId().equals(scan.projectId()) && s.isRunning());
        if (running) {
            throw new ScanAlreadyRunningException();
        }
        db.scans.put(scan.id(), scan);
    }

    @Override
    public boolean finishIfRunning(UUID scanId, ScanStatus outcome, Instant at) {
        Scan scan = db.scans.get(scanId);
        if (scan == null || !scan.isRunning()) {
            return false;
        }
        db.scans.put(scanId, scan.finish(outcome, at));
        return true;
    }
}
