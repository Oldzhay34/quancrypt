package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.event.PlanItemTransitioned;
import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.IllegalStateTransitionException;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.PlanItemTransition;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemUseCase;
import com.quancrypt.core.port.inbound.view.PlanItemView;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.PlanReader;
import com.quancrypt.core.port.outbound.PlanWriter;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.RiskThresholdReader;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.Optional;
import java.util.UUID;

/** Moves a plan item to another state with optimistic locking and an allowed-transition check (State pattern). */
public final class TransitionPlanItemService implements TransitionPlanItemUseCase {

    private final TransactionRunner tx;
    private final ProjectLock projectLock;
    private final ConsentGate consentGate;
    private final PlanReader planReader;
    private final PlanWriter planWriter;
    private final RiskThresholdReader thresholds;
    private final EventRecorder events;
    private final IdempotentExecutor idempotency;
    private final AuditRecorder audit;
    private final Clock clock;
    private final IdGenerator ids;

    public TransitionPlanItemService(
            TransactionRunner tx, ProjectLock projectLock, ConsentGate consentGate, PlanReader planReader, PlanWriter planWriter,
            RiskThresholdReader thresholds, EventRecorder events, IdempotentExecutor idempotency, AuditRecorder audit,
            Clock clock, IdGenerator ids) {
        this.tx = tx;
        this.projectLock = projectLock;
        this.consentGate = consentGate;
        this.planReader = planReader;
        this.planWriter = planWriter;
        this.thresholds = thresholds;
        this.events = events;
        this.idempotency = idempotency;
        this.audit = audit;
        this.clock = clock;
        this.ids = ids;
    }

    @Override
    public PlanItemView execute(TransitionPlanItemCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        PlanItemStateCode target = Codes.parse(PlanItemStateCode.class, input.toState(), "toState");
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> idempotency.execute(
                input.idempotency(),
                AuditAction.PLAN_ITEM_TRANSITIONED,
                replay -> planReader.item(input.itemId()).map(i -> ViewMapper.planItem(i, thresholds.policy())).orElseThrow(() -> Fail.notFound("plan item")),
                () -> {
                    UUID projectId = planReader.projectIdOfItem(input.itemId()).orElseThrow(() -> Fail.notFound("plan item"));
                    Project project = projectLock.keyShare(projectId).orElseThrow(() -> Fail.notFound("project"));
                    boolean consented = consentGate.warehouseConsented(project.id());
                    PlanItem item = planReader.item(input.itemId()).orElseThrow(() -> Fail.notFound("plan item"));
                    if (input.expectedVersion() != item.version()) {
                        throw Fail.problem(ProblemCode.CONCURRENT_MODIFICATION, "the plan item was changed by someone else");
                    }
                    PlanItem moved;
                    try {
                        moved = item.transitionTo(target);
                    } catch (IllegalStateTransitionException e) {
                        throw Fail.problem(ProblemCode.INVALID_STATE_TRANSITION, e.getMessage());
                    }
                    PlanItemTransition transition = new PlanItemTransition(ids.next(), item.id(), item.state().code(), target, clock.now(), caller);
                    try {
                        planWriter.update(moved, input.expectedVersion(), transition);
                    } catch (ConcurrentModificationException e) {
                        throw Fail.problem(ProblemCode.CONCURRENT_MODIFICATION, e.getMessage());
                    }
                    events.recordIfConsented(consented, project.key(),
                            new PlanItemTransitioned(item.strategy(), item.effort(), item.state().code(), target));
                    audit.record(AuditAction.PLAN_ITEM_TRANSITIONED, Optional.of(project.key()), Optional.of(item.id()), caller);
                    return new IdempotentExecutor.Outcome<>(ViewMapper.planItem(moved, thresholds.policy()), 200, Optional.of(item.id()));
                }));
    }
}
