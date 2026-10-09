package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.port.inbound.ListFindingsQuery;
import com.quancrypt.core.port.inbound.ListFindingsUseCase;
import com.quancrypt.core.port.inbound.view.FindingView;
import com.quancrypt.core.port.inbound.view.PageView;
import com.quancrypt.core.port.outbound.FindingFilter;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ScanReader;
import com.quancrypt.core.port.outbound.TransactionRunner;

/** Lists the findings of a scan with optional filters. */
public final class ListFindingsService implements ListFindingsUseCase {

    private final TransactionRunner tx;
    private final ScanReader scans;
    private final FindingReader findings;

    public ListFindingsService(TransactionRunner tx, ScanReader scans, FindingReader findings) {
        this.tx = tx;
        this.scans = scans;
        this.findings = findings;
    }

    @Override
    public PageView<FindingView> execute(ListFindingsQuery input) {
        Guard.page(input.page(), input.size());
        FindingFilter filter = new FindingFilter(
                Codes.parseOptional(Priority.class, input.priority(), "priority"),
                Codes.parseOptional(AlgorithmFamily.class, input.algorithmFamily(), "algorithmFamily"),
                Codes.parseOptional(UsageContext.class, input.usageContext(), "usageContext"),
                Codes.parseOptional(LocationKind.class, input.locationKind(), "locationKind"),
                Codes.parseOptional(ClassifiedBy.class, input.classifiedBy(), "classifiedBy"));
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            scans.find(input.scanId()).orElseThrow(() -> Fail.notFound("scan"));
            return ViewMapper.page(findings.page(input.scanId(), filter, input.page(), input.size()), ViewMapper::finding);
        });
    }
}
