package com.quancrypt.core.api.controller;

import com.quancrypt.core.api.RequestSupport;
import com.quancrypt.core.facade.ProjectFacade;
import com.quancrypt.core.facade.dto.ClarificationAnswerSetDto;
import com.quancrypt.core.facade.dto.ClarificationAnswerSetInput;
import com.quancrypt.core.facade.dto.Outcome;
import com.quancrypt.core.facade.dto.PageDto;
import com.quancrypt.core.facade.dto.ProjectDetailDto;
import com.quancrypt.core.facade.dto.ProjectDto;
import com.quancrypt.core.facade.dto.ProjectProfileDto;
import com.quancrypt.core.facade.dto.ProjectRegistrationInput;
import com.quancrypt.core.facade.dto.RuntimeProfileDto;
import com.quancrypt.core.facade.dto.RuntimeProfileInput;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Projects, their runtime profiles, clarification answers and profile. */
@RestController
@RequestMapping("/api/v1/projects")
public class ProjectController {

    private final ProjectFacade projects;

    public ProjectController(ProjectFacade projects) {
        this.projects = projects;
    }

    @PostMapping
    ResponseEntity<ProjectDto> register(
            @Valid @RequestBody ProjectRegistrationInput body,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        Outcome<ProjectDto> outcome = projects.register(body, RequestSupport.key(idempotencyKey), RequestSupport.caller(authentication));
        return ResponseEntity.status(outcome.created() ? HttpStatus.CREATED : HttpStatus.OK).body(outcome.body());
    }

    @GetMapping
    PageDto<ProjectDto> list(@RequestParam(defaultValue = "0") @Min(0) int page, @RequestParam(defaultValue = "50") @Min(1) @Max(200) int size) {
        return projects.list(page, size);
    }

    @GetMapping("/{projectId}")
    ProjectDetailDto get(@PathVariable UUID projectId) {
        return projects.get(projectId);
    }

    @DeleteMapping("/{projectId}")
    ResponseEntity<Void> delete(@PathVariable UUID projectId, Authentication authentication) {
        projects.delete(projectId, RequestSupport.caller(authentication));
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{projectId}/runtime-profiles")
    ResponseEntity<RuntimeProfileDto> recordRuntimeProfile(
            @PathVariable UUID projectId,
            @Valid @RequestBody RuntimeProfileInput body,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        Outcome<RuntimeProfileDto> outcome =
                projects.recordRuntimeProfile(projectId, body, RequestSupport.key(idempotencyKey), RequestSupport.caller(authentication));
        return ResponseEntity.status(outcome.created() ? HttpStatus.CREATED : HttpStatus.OK).body(outcome.body());
    }

    @PutMapping("/{projectId}/clarification-answers")
    ClarificationAnswerSetDto saveClarificationAnswers(
            @PathVariable UUID projectId, @Valid @RequestBody ClarificationAnswerSetInput body, Authentication authentication) {
        return projects.saveClarificationAnswers(projectId, body, RequestSupport.caller(authentication));
    }

    @GetMapping("/{projectId}/profile")
    ProjectProfileDto profile(@PathVariable UUID projectId) {
        return projects.profile(projectId);
    }
}
