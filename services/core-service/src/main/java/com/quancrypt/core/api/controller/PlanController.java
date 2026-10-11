package com.quancrypt.core.api.controller;

import com.quancrypt.core.api.RequestSupport;
import com.quancrypt.core.facade.PlanFacade;
import com.quancrypt.core.facade.dto.PlanDto;
import com.quancrypt.core.facade.dto.PlanInput;
import com.quancrypt.core.facade.dto.PlanItemDto;
import com.quancrypt.core.facade.dto.PlanItemTransitionInput;
import com.quancrypt.core.facade.dto.PlanPageDto;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Plans, plan item transitions and the Markdown report. */
@RestController
@RequestMapping("/api/v1")
public class PlanController {

    private static final MediaType MARKDOWN = new MediaType("text", "markdown", StandardCharsets.UTF_8);

    private final PlanFacade plans;

    public PlanController(PlanFacade plans) {
        this.plans = plans;
    }

    @PostMapping("/scans/{scanId}/plan")
    ResponseEntity<PlanDto> create(
            @PathVariable UUID scanId,
            @Valid @RequestBody PlanInput body,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(plans.create(scanId, body, RequestSupport.key(idempotencyKey), RequestSupport.caller(authentication)));
    }

    @GetMapping("/scans/{scanId}/plan")
    PlanPageDto get(
            @PathVariable UUID scanId,
            @RequestParam(required = false) String state,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int size) {
        return plans.get(scanId, state, page, size);
    }

    @PostMapping("/plan-items/{itemId}/transitions")
    ResponseEntity<PlanItemDto> transition(
            @PathVariable UUID itemId,
            @Valid @RequestBody PlanItemTransitionInput body,
            @RequestHeader(name = "If-Match", required = false) String ifMatch,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        PlanItemDto item = plans.transition(itemId, body, RequestSupport.requiredVersion(ifMatch), RequestSupport.key(idempotencyKey),
                RequestSupport.caller(authentication));
        return ResponseEntity.ok().eTag("\"" + item.version() + "\"").body(item);
    }

    @GetMapping(value = "/scans/{scanId}/plan/report", produces = "text/markdown;charset=UTF-8")
    ResponseEntity<String> report(
            @PathVariable UUID scanId, @RequestHeader(name = HttpHeaders.ACCEPT_LANGUAGE, required = false) String acceptLanguage) {
        return ResponseEntity.ok().contentType(MARKDOWN).body(plans.report(scanId, acceptLanguage));
    }
}
