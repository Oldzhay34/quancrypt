package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.domain.model.ClarificationQuestion;
import com.quancrypt.core.domain.model.Project;
import com.quancrypt.core.port.inbound.ClarificationAnswerInput;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersCommand;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersUseCase;
import com.quancrypt.core.port.inbound.view.ProjectProfileView;
import com.quancrypt.core.port.outbound.ClarificationReader;
import com.quancrypt.core.port.outbound.ClarificationWriter;
import com.quancrypt.core.port.outbound.Clock;
import com.quancrypt.core.port.outbound.IsolationLevel;
import com.quancrypt.core.port.outbound.ProjectLock;
import com.quancrypt.core.port.outbound.RuntimeProfileReader;
import com.quancrypt.core.port.outbound.TransactionRunner;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/** Saves the clarification answers of a project profile (up to five, one per question). */
public final class SaveClarificationAnswersService implements SaveClarificationAnswersUseCase {

    private final TransactionRunner tx;
    private final ProjectLock projectLock;
    private final ClarificationReader reader;
    private final ClarificationWriter writer;
    private final RuntimeProfileReader profiles;
    private final AuditRecorder audit;
    private final Clock clock;

    public SaveClarificationAnswersService(
            TransactionRunner tx, ProjectLock projectLock, ClarificationReader reader, ClarificationWriter writer,
            RuntimeProfileReader profiles, AuditRecorder audit, Clock clock) {
        this.tx = tx;
        this.projectLock = projectLock;
        this.reader = reader;
        this.writer = writer;
        this.profiles = profiles;
        this.audit = audit;
        this.clock = clock;
    }

    @Override
    public ProjectProfileView execute(SaveClarificationAnswersCommand input) {
        CallerKind caller = Codes.caller(input.caller());
        int questions = ClarificationQuestion.values().length;
        if (input.answers().isEmpty() || input.answers().size() > questions) {
            throw Fail.validation("1.." + questions + " answers are expected");
        }
        List<ClarificationAnswer> answers = new ArrayList<>();
        Set<ClarificationQuestion> seen = new HashSet<>();
        for (ClarificationAnswerInput in : input.answers()) {
            ClarificationQuestion question = Codes.parse(ClarificationQuestion.class, in.questionCode(), "questionCode");
            if (!seen.add(question)) {
                throw Fail.validation("each question is answered once");
            }
            answers.add(Guard.valid(() -> new ClarificationAnswer(question, in.optionCode(), in.freeText(), clock.now())));
        }
        return tx.inTransaction(IsolationLevel.READ_COMMITTED, () -> {
            Project project = projectLock.keyShare(input.projectId()).orElseThrow(() -> Fail.notFound("project"));
            writer.upsertAll(project.id(), answers);
            audit.record(AuditAction.CLARIFICATION_ANSWERS_SAVED, Optional.of(project.key()), Optional.of(project.id()), caller);
            return new ProjectProfileView(
                    profiles.current(project.id()).map(p -> ViewMapper.runtimeProfile(p, false)),
                    reader.list(project.id()).stream().map(ViewMapper::answer).toList());
        });
    }
}
