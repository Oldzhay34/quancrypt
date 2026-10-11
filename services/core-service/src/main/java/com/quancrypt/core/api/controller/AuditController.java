package com.quancrypt.core.api.controller;

import com.quancrypt.core.facade.AuditFacade;
import com.quancrypt.core.facade.dto.AuditEntryDto;
import com.quancrypt.core.facade.dto.PageDto;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** The audit log of a project (the project key is the anonymous HMAC key, never a path). */
@RestController
@RequestMapping("/api/v1/audit-entries")
public class AuditController {

    private final AuditFacade audit;

    public AuditController(AuditFacade audit) {
        this.audit = audit;
    }

    @GetMapping
    PageDto<AuditEntryDto> entries(
            @RequestParam @Pattern(regexp = "^[0-9a-f]{64}$") String projectKey,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int size) {
        return audit.entries(projectKey, page, size);
    }
}
