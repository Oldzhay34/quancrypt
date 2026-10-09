package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.domain.model.ScanStatus;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.ScanLock;
import com.quancrypt.core.port.outbound.ScanReader;
import java.util.UUID;

/** Locks a scan's rows in the binding order: project, then consent, then scan (D-143). */
public final class ScanAccess {

    private final ScanReader scans;
    private final ProjectLock projectLock;
    private final ScanLock scanLock;
    private final ConsentGate consentGate;

    public ScanAccess(ScanReader scans, ProjectLock projectLock, ScanLock scanLock, ConsentGate consentGate) {
        this.scans = scans;
        this.projectLock = projectLock;
        this.scanLock = scanLock;
        this.consentGate = consentGate;
    }

    /** For writers that add to a running scan; the scan row is locked FOR NO KEY UPDATE. */
    LockedScan runningForUpdate(UUID scanId) {
        Project project = lockProject(scanId);
        boolean consent = consentGate.warehouseConsented(project.id());
        Scan scan = scanLock.noKeyUpdate(scanId).orElseThrow(() -> Fail.notFound("scan"));
        if (!scan.isRunning()) {
            throw Fail.problem(ProblemCode.SCAN_NOT_RUNNING, "the scan is not running");
        }
        return new LockedScan(project, scan, consent);
    }

    /** For CompleteScan: project and consent are locked, the scan is changed by a conditional update. */
    LockedScan forCompletion(UUID scanId) {
        Project project = lockProject(scanId);
        boolean consent = consentGate.warehouseConsented(project.id());
        Scan scan = scans.find(scanId).orElseThrow(() -> Fail.notFound("scan"));
        return new LockedScan(project, scan, consent);
    }

    /** For CreatePlan; the scan row is locked FOR SHARE and must be completed. */
    LockedScan completedForShare(UUID scanId) {
        Project project = lockProject(scanId);
        boolean consent = consentGate.warehouseConsented(project.id());
        Scan scan = scanLock.share(scanId).orElseThrow(() -> Fail.notFound("scan"));
        if (scan.status() != ScanStatus.COMPLETED) {
            throw Fail.problem(ProblemCode.SCAN_NOT_COMPLETED, "the scan is not completed");
        }
        return new LockedScan(project, scan, consent);
    }

    private Project lockProject(UUID scanId) {
        UUID projectId = scans.projectIdOf(scanId).orElseThrow(() -> Fail.notFound("scan"));
        return projectLock.keyShare(projectId).orElseThrow(() -> Fail.notFound("project"));
    }
}
