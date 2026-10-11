package com.quancrypt.core.api.controller;

import com.quancrypt.core.api.RequestSupport;
import com.quancrypt.core.facade.ProjectFacade;
import com.quancrypt.core.facade.dto.ConsentDto;
import com.quancrypt.core.facade.dto.ConsentGrantInput;
import com.quancrypt.core.facade.dto.ConsentListDto;
import com.quancrypt.core.facade.dto.Outcome;
import com.quancrypt.core.facade.dto.PrivacyNoticeDto;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** The privacy notice and the consents of a project. */
@RestController
@RequestMapping("/api/v1")
public class ConsentController {

    private final ProjectFacade projects;

    public ConsentController(ProjectFacade projects) {
        this.projects = projects;
    }

    @GetMapping("/privacy-notices/latest")
    PrivacyNoticeDto latestPrivacyNotice() {
        return projects.latestPrivacyNotice();
    }

    @PostMapping("/projects/{projectId}/consents")
    ResponseEntity<ConsentDto> grant(
            @PathVariable UUID projectId,
            @Valid @RequestBody ConsentGrantInput body,
            @RequestHeader(name = "If-Match", required = false) String ifMatch,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        Outcome<ConsentDto> outcome = projects.grantConsent(projectId, body, RequestSupport.optionalVersion(ifMatch),
                RequestSupport.key(idempotencyKey), RequestSupport.caller(authentication));
        return ResponseEntity.status(outcome.created() ? HttpStatus.CREATED : HttpStatus.OK)
                .eTag("\"" + outcome.body().version() + "\"").body(outcome.body());
    }

    @GetMapping("/projects/{projectId}/consents")
    ConsentListDto consents(@PathVariable UUID projectId) {
        return projects.consents(projectId);
    }

    @DeleteMapping("/projects/{projectId}/consents/{consentType}")
    ResponseEntity<ConsentDto> revoke(
            @PathVariable UUID projectId, @PathVariable String consentType,
            @RequestHeader(name = "If-Match", required = false) String ifMatch, Authentication authentication) {
        ConsentDto consent = projects.revokeConsent(projectId, consentType, RequestSupport.requiredVersion(ifMatch),
                RequestSupport.caller(authentication));
        return ResponseEntity.ok().eTag("\"" + consent.version() + "\"").body(consent);
    }
}
