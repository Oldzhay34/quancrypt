package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.Scan;
import com.quancrypt.core.port.inbound.GetScanSummaryQuery;
import com.quancrypt.core.port.inbound.GetScanSummaryUseCase;
import com.quancrypt.core.port.inbound.view.RuntimeProfileView;
import com.quancrypt.core.port.inbound.view.ScanSummaryView;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.FindingStats;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

/** Reads a scan with its runtime profile and finding counts. */
public final class GetScanSummaryService implements GetScanSummaryUseCase {

    private final TransactionRunner tx;
    private final ScanReader scans;
    private final RuntimeProfileReader profiles;
    private final FindingReader findings;

    public GetScanSummaryService(TransactionRunner tx, ScanReader scans, RuntimeProfileReader profiles, FindingReader findings) {
        this.tx = tx;
        this.scans = scans;
        this.profiles = profiles;
        this.findings = findings;
    }

    @Override
    public ScanSummaryView execute(GetScanSummaryQuery input) {
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            Scan scan = scans.find(input.scanId()).orElseThrow(() -> Fail.notFound("scan"));
            Optional<RuntimeProfileView> profile = scan.runtimeProfileSequenceNo()
                    .flatMap(seq -> profiles.bySequence(scan.projectId(), seq))
                    .map(p -> ViewMapper.runtimeProfile(p, false));
            FindingStats stats = findings.stats(scan.id());
            return new ScanSummaryView(ViewMapper.scan(scan), profile, stats.total(),
                    named(stats.byPriority()), named(stats.byAlgorithmFamily()), named(stats.byLocationKind()));
        });
    }

    private static <K extends Enum<K>> Map<String, Integer> named(Map<K, Integer> counts) {
        return counts.entrySet().stream().collect(Collectors.toMap(e -> e.getKey().name(), Map.Entry::getValue));
    }
}
