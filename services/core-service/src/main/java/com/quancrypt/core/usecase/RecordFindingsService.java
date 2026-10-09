package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.FindingDetected;
import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.Finding;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.port.inbound.FindingInput;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.RecordFindingsUseCase;
import com.quancrypt.core.port.inbound.view.RecordFindingsResult;
import com.quancrypt.core.port.outbound.FindingReader;
import com.quancrypt.core.port.outbound.FindingWriter;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

/** Records a batch of findings of a running scan: validates priorities, resolves files, writes events (D-141, D-149). */
public final class RecordFindingsService implements RecordFindingsUseCase {

    static final int MAX_BATCH = 500;
    static final int MAX_FINDINGS_PER_SCAN = 500;

    private record Parsed(
            String path, LocationKind kind, String symbol, AlgorithmFamily algorithm, UsageContext usage, Priority priority,
            Optional<Integer> keySizeBits, Optional<Integer> lineStart, Optional<Integer> lineEnd, double confidence, ClassifiedBy by) {
    }

    private final TransactionRunner tx;
    private final ScanAccess access;
    private final SourceFileResolver files;
    private final FindingReader findingReader;
    private final FindingWriter findingWriter;
    private final FindingValidator validator;
    private final EventRecorder events;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final IdGenerator ids;

    public RecordFindingsService(
            TransactionRunner tx, ScanAccess access, SourceFileResolver files, FindingReader findingReader,
            FindingWriter findingWriter, FindingValidator validator, EventRecorder events, IdempotentExecutor idempotency,
            AuditRecorder audit, IdGenerator ids) {
        this.tx = tx;
        this.access = access;
        this.files = files;
        this.findingReader = findingReader;
        this.findingWriter = findingWriter;
        this.validator = validator;
        this.events = events;
        this.idempotency = idempotency;
        this.audit = audit;
        this.ids = ids;
    }

    @Override
    public RecordFindingsResult execute(RecordFindingsCommand input) {
        if (input.findings().isEmpty() || input.findings().size() > MAX_BATCH) {
            throw Fail.validation("a batch holds 1.." + MAX_BATCH + " findings");
        }
        CallerKind caller = Codes.caller(input.caller());
        List<Parsed> parsed = input.findings().stream().map(this::parse).toList();
        Map<String, LocationKind> kinds = SourceFileResolver.kindsByPath(parsed.stream().map(p -> new PathKind(p.path(), p.kind())).toList());
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                input.idempotency(),
                AuditAction.FINDINGS_RECORDED,
                replay -> new RecordFindingsResult(0, parsed.size(), List.of()),
                () -> {
                    LockedScan locked = access.runningForUpdate(input.scanId());
                    Map<String, SourceFile> resolved = files.resolve(locked.scan().id(), kinds);
                    List<Finding> findings = parsed.stream().map(p -> toFinding(p, resolved.get(p.path()))).toList();
                    Set<UUID> inserted = new HashSet<>(findingWriter.insertIgnoringDuplicates(findings));
                    if (findingReader.countByScan(locked.scan().id()) > MAX_FINDINGS_PER_SCAN) {
                        throw Fail.problem(ProblemCode.FINDING_LIMIT_EXCEEDED, "a scan holds at most " + MAX_FINDINGS_PER_SCAN + " findings");
                    }
                    for (int i = 0; i < findings.size(); i++) {
                        Finding f = findings.get(i);
                        if (inserted.contains(f.id())) {
                            events.recordIfConsented(locked.warehouseConsent(), locked.project().key(), new FindingDetected(
                                    f.algorithm(), f.usage(), parsed.get(i).kind(), f.priority(), f.keySizeBits(), f.confidence(), f.classifiedBy()));
                        }
                    }
                    audit.record(AuditAction.FINDINGS_RECORDED, Optional.of(locked.project().key()), Optional.of(locked.scan().id()), caller);
                    List<UUID> createdIds = findings.stream().map(Finding::id).filter(inserted::contains).toList();
                    RecordFindingsResult result = new RecordFindingsResult(createdIds.size(), findings.size() - createdIds.size(), createdIds);
                    return new IdempotentExecutor.Outcome<>(result, 201, Optional.of(locked.scan().id()));
                }));
    }

    private Finding toFinding(Parsed p, SourceFile file) {
        return new Finding(ids.next(), file.id(), p.symbol(), p.algorithm(), p.usage(), p.priority(), p.keySizeBits(),
                p.lineStart(), p.lineEnd(), p.confidence(), p.by());
    }

    private Parsed parse(FindingInput in) {
        AlgorithmFamily algorithm = Codes.parse(AlgorithmFamily.class, in.algorithmFamily(), "algorithmFamily");
        UsageContext usage = Codes.parse(UsageContext.class, in.usageContext(), "usageContext");
        LocationKind kind = Codes.parse(LocationKind.class, in.locationKind(), "locationKind");
        Priority supplied = Codes.parse(Priority.class, in.priority(), "priority");
        ClassifiedBy by = Codes.parse(ClassifiedBy.class, in.classifiedBy(), "classifiedBy");
        Guard.valid(() -> new SourceFile(new UUID(0, 0), new UUID(0, 0), in.path(), kind));
        Guard.valid(() -> new Finding(new UUID(0, 0), new UUID(0, 0), in.symbol(), algorithm, usage, supplied, in.keySizeBits(),
                in.lineStart(), in.lineEnd(), in.confidence(), by));
        Priority priority = validator.acceptedPriority(new CryptoUsage(algorithm, usage, in.keySizeBits(), kind), supplied);
        return new Parsed(in.path(), kind, in.symbol(), algorithm, usage, priority, in.keySizeBits(), in.lineStart(), in.lineEnd(),
                in.confidence(), by);
    }
}
