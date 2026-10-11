package com.quancrypt.core.facade;

import com.quancrypt.core.facade.dto.ClarificationAnswerDto;
import com.quancrypt.core.facade.dto.ClarificationAnswerSetDto;
import com.quancrypt.core.facade.dto.ClarificationAnswerSetInput;
import com.quancrypt.core.facade.dto.ConsentDto;
import com.quancrypt.core.facade.dto.ConsentGrantInput;
import com.quancrypt.core.facade.dto.ConsentListDto;
import com.quancrypt.core.facade.dto.Outcome;
import com.quancrypt.core.facade.dto.PageDto;
import com.quancrypt.core.facade.dto.PrivacyNoticeDto;
import com.quancrypt.core.facade.dto.ProjectDetailDto;
import com.quancrypt.core.facade.dto.ProjectDto;
import com.quancrypt.core.facade.dto.ProjectProfileDto;
import com.quancrypt.core.facade.dto.ProjectRegistrationInput;
import com.quancrypt.core.facade.dto.RuntimeProfileDto;
import com.quancrypt.core.facade.dto.RuntimeProfileInput;
import com.quancrypt.core.port.inbound.ClarificationAnswerInput;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.DeleteProjectUseCase;
import com.quancrypt.core.port.inbound.GetConsentsQuery;
import com.quancrypt.core.port.inbound.GetConsentsUseCase;
import com.quancrypt.core.port.inbound.GetPrivacyNoticeQuery;
import com.quancrypt.core.port.inbound.GetPrivacyNoticeUseCase;
import com.quancrypt.core.port.inbound.GetProjectProfileQuery;
import com.quancrypt.core.port.inbound.GetProjectProfileUseCase;
import com.quancrypt.core.port.inbound.GetProjectQuery;
import com.quancrypt.core.port.inbound.GetProjectUseCase;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.GrantConsentUseCase;
import com.quancrypt.core.port.inbound.ListProjectsQuery;
import com.quancrypt.core.port.inbound.ListProjectsUseCase;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileUseCase;
import com.quancrypt.core.port.inbound.RegisterProjectCommand;
import com.quancrypt.core.port.inbound.RegisterProjectUseCase;
import com.quancrypt.core.port.inbound.RevokeConsentCommand;
import com.quancrypt.core.port.inbound.RevokeConsentUseCase;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersCommand;
import com.quancrypt.core.port.inbound.SaveClarificationAnswersUseCase;
import com.quancrypt.core.port.inbound.view.ProjectDetailView;
import com.quancrypt.core.port.inbound.view.ProjectProfileView;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Projects, runtime profiles, clarification answers and consents. */
public final class ProjectFacade {

    private final RegisterProjectUseCase registerProject;
    private final ListProjectsUseCase listProjects;
    private final GetProjectUseCase getProject;
    private final DeleteProjectUseCase deleteProject;
    private final RecordRuntimeProfileUseCase recordRuntimeProfile;
    private final GetPrivacyNoticeUseCase getPrivacyNotice;
    private final GrantConsentUseCase grantConsent;
    private final RevokeConsentUseCase revokeConsent;
    private final GetConsentsUseCase getConsents;
    private final SaveClarificationAnswersUseCase saveClarificationAnswers;
    private final GetProjectProfileUseCase getProjectProfile;

    public ProjectFacade(
            RegisterProjectUseCase registerProject, ListProjectsUseCase listProjects, GetProjectUseCase getProject,
            DeleteProjectUseCase deleteProject, RecordRuntimeProfileUseCase recordRuntimeProfile,
            GetPrivacyNoticeUseCase getPrivacyNotice, GrantConsentUseCase grantConsent, RevokeConsentUseCase revokeConsent,
            GetConsentsUseCase getConsents, SaveClarificationAnswersUseCase saveClarificationAnswers,
            GetProjectProfileUseCase getProjectProfile) {
        this.registerProject = registerProject;
        this.listProjects = listProjects;
        this.getProject = getProject;
        this.deleteProject = deleteProject;
        this.recordRuntimeProfile = recordRuntimeProfile;
        this.getPrivacyNotice = getPrivacyNotice;
        this.grantConsent = grantConsent;
        this.revokeConsent = revokeConsent;
        this.getConsents = getConsents;
        this.saveClarificationAnswers = saveClarificationAnswers;
        this.getProjectProfile = getProjectProfile;
    }

    public Outcome<ProjectDto> register(ProjectRegistrationInput body, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> {
            var view = registerProject.execute(new RegisterProjectCommand(body.identity(), body.displayName(), idempotencyKey, caller));
            return new Outcome<>(view.created(), FacadeMapper.project(view));
        });
    }

    public PageDto<ProjectDto> list(int page, int size) {
        return ProblemTranslator.call(() -> FacadeMapper.page(listProjects.execute(new ListProjectsQuery(page, size)), FacadeMapper::project));
    }

    public ProjectDetailDto get(UUID projectId) {
        return ProblemTranslator.call(() -> {
            ProjectDetailView view = getProject.execute(new GetProjectQuery(projectId));
            return new ProjectDetailDto(FacadeMapper.project(view.project()), FacadeMapper.runtimeProfile(view.currentRuntimeProfile()));
        });
    }

    public void delete(UUID projectId, String caller) {
        ProblemTranslator.run(() -> deleteProject.execute(new DeleteProjectCommand(projectId, caller)));
    }

    public Outcome<RuntimeProfileDto> recordRuntimeProfile(
            UUID projectId, RuntimeProfileInput body, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> {
            var view = recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(projectId, body.javaVersion(),
                    Optional.ofNullable(body.springBootVersion()),
                    Idem.of(idempotencyKey, "POST", "/api/v1/projects/{projectId}/runtime-profiles", body, projectId.toString()), caller));
            return new Outcome<>(view.created(), FacadeMapper.runtimeProfile(view));
        });
    }

    public PrivacyNoticeDto latestPrivacyNotice() {
        return ProblemTranslator.call(() -> FacadeMapper.notice(getPrivacyNotice.execute(new GetPrivacyNoticeQuery())));
    }

    public Outcome<ConsentDto> grantConsent(
            UUID projectId, ConsentGrantInput body, Optional<Integer> expectedVersion, Optional<String> idempotencyKey, String caller) {
        return ProblemTranslator.call(() -> {
            var view = grantConsent.execute(new GrantConsentCommand(projectId, body.consentType(), body.privacyNoticeVersion(), expectedVersion,
                    Idem.of(idempotencyKey, "POST", "/api/v1/projects/{projectId}/consents", body, projectId.toString()), caller));
            return new Outcome<>(view.created(), FacadeMapper.consent(view));
        });
    }

    public ConsentListDto consents(UUID projectId) {
        return ProblemTranslator.call(() -> new ConsentListDto(
                getConsents.execute(new GetConsentsQuery(projectId)).items().stream().map(FacadeMapper::consent).toList()));
    }

    public ConsentDto revokeConsent(UUID projectId, String consentType, int expectedVersion, String caller) {
        return ProblemTranslator.call(() -> FacadeMapper.consent(
                revokeConsent.execute(new RevokeConsentCommand(projectId, consentType, expectedVersion, caller))));
    }

    public ClarificationAnswerSetDto saveClarificationAnswers(UUID projectId, ClarificationAnswerSetInput body, String caller) {
        return ProblemTranslator.call(() -> {
            List<ClarificationAnswerInput> answers = body.answers().stream()
                    .map(a -> new ClarificationAnswerInput(a.questionCode(), Optional.ofNullable(a.optionCode()), Optional.ofNullable(a.freeText())))
                    .toList();
            return new ClarificationAnswerSetDto(FacadeMapper.answers(
                    saveClarificationAnswers.execute(new SaveClarificationAnswersCommand(projectId, answers, caller)).answers()));
        });
    }

    public ProjectProfileDto profile(UUID projectId) {
        return ProblemTranslator.call(() -> profile(getProjectProfile.execute(new GetProjectProfileQuery(projectId))));
    }

    private static ProjectProfileDto profile(ProjectProfileView view) {
        List<ClarificationAnswerDto> answers = FacadeMapper.answers(view.answers());
        return new ProjectProfileDto(FacadeMapper.runtimeProfile(view.runtimeProfile()), answers);
    }
}
