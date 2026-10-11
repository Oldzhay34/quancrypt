package com.quancrypt.core.api.controller;

import com.quancrypt.core.api.RequestSupport;
import com.quancrypt.core.facade.ScanFacade;
import com.quancrypt.core.facade.dto.ArtifactContent;
import com.quancrypt.core.facade.dto.FindingBatchInput;
import com.quancrypt.core.facade.dto.FindingBatchResultDto;
import com.quancrypt.core.facade.dto.FindingDto;
import com.quancrypt.core.facade.dto.PageDto;
import com.quancrypt.core.facade.dto.ScanArtifactDto;
import com.quancrypt.core.facade.dto.ScanCompletionInput;
import com.quancrypt.core.facade.dto.ScanDto;
import com.quancrypt.core.facade.dto.ScanSummaryDto;
import com.quancrypt.core.facade.dto.TopologyDto;
import com.quancrypt.core.facade.dto.TopologyInput;
import com.quancrypt.core.facade.error.ApiProblemException;
import com.quancrypt.core.facade.error.ProblemKind;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import java.io.IOException;
import java.io.InputStream;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Scans, findings, topology and the CBOM file of a scan. */
@RestController
@RequestMapping("/api/v1")
public class ScanController {

    /** 20 MiB, the limit of the contract (413 payload-too-large). */
    static final int MAX_ARTIFACT_BYTES = 20 * 1024 * 1024;

    private final ScanFacade scans;

    public ScanController(ScanFacade scans) {
        this.scans = scans;
    }

    @PostMapping("/projects/{projectId}/scans")
    ResponseEntity<ScanDto> start(
            @PathVariable UUID projectId,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(scans.start(projectId, RequestSupport.key(idempotencyKey), RequestSupport.caller(authentication)));
    }

    @GetMapping("/projects/{projectId}/scans")
    PageDto<ScanDto> list(
            @PathVariable UUID projectId, @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int size) {
        return scans.list(projectId, page, size);
    }

    @GetMapping("/scans/{scanId}")
    ScanSummaryDto summary(@PathVariable UUID scanId) {
        return scans.summary(scanId);
    }

    @PostMapping("/scans/{scanId}/findings")
    ResponseEntity<FindingBatchResultDto> recordFindings(
            @PathVariable UUID scanId,
            @Valid @RequestBody FindingBatchInput body,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(scans.recordFindings(scanId, body, RequestSupport.key(idempotencyKey), RequestSupport.caller(authentication)));
    }

    @GetMapping("/scans/{scanId}/findings")
    PageDto<FindingDto> findings(
            @PathVariable UUID scanId,
            @RequestParam(required = false) String priority,
            @RequestParam(required = false) String algorithmFamily,
            @RequestParam(required = false) String usageContext,
            @RequestParam(required = false) String locationKind,
            @RequestParam(required = false) String classifiedBy,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int size) {
        return scans.findings(scanId, priority, algorithmFamily, usageContext, locationKind, classifiedBy, page, size);
    }

    @GetMapping("/findings/{findingId}")
    FindingDto finding(@PathVariable UUID findingId) {
        return scans.finding(findingId);
    }

    @PutMapping("/scans/{scanId}/topology")
    TopologyDto recordTopology(@PathVariable UUID scanId, @Valid @RequestBody TopologyInput body, Authentication authentication) {
        return scans.recordTopology(scanId, body, RequestSupport.caller(authentication));
    }

    @GetMapping("/scans/{scanId}/topology")
    TopologyDto topology(@PathVariable UUID scanId) {
        return scans.topology(scanId);
    }

    @PutMapping("/scans/{scanId}/artifact")
    ScanArtifactDto recordArtifact(@PathVariable UUID scanId, HttpServletRequest request, Authentication authentication) throws IOException {
        long declared = request.getContentLengthLong();
        if (declared > MAX_ARTIFACT_BYTES) {
            throw tooLarge();
        }
        byte[] content;
        try (InputStream in = request.getInputStream()) {
            content = in.readNBytes(MAX_ARTIFACT_BYTES + 1);
        }
        if (content.length > MAX_ARTIFACT_BYTES) {
            throw tooLarge();
        }
        return scans.recordArtifact(scanId, baseMediaType(request.getContentType()), content, RequestSupport.caller(authentication));
    }

    @GetMapping("/scans/{scanId}/artifact")
    ResponseEntity<byte[]> artifact(@PathVariable UUID scanId) {
        ArtifactContent file = scans.artifact(scanId);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(file.contentType()))
                .header(HttpHeaders.ETAG, "\"" + file.sha256() + "\"")
                .body(file.content());
    }

    @PostMapping("/scans/{scanId}/completion")
    ScanDto complete(
            @PathVariable UUID scanId,
            @Valid @RequestBody ScanCompletionInput body,
            @RequestHeader(name = "Idempotency-Key", required = false) @Size(min = 1, max = 128) String idempotencyKey,
            Authentication authentication) {
        return scans.complete(scanId, body, RequestSupport.key(idempotencyKey), RequestSupport.caller(authentication));
    }

    private static ApiProblemException tooLarge() {
        return new ApiProblemException(ProblemKind.PAYLOAD_TOO_LARGE, "the artifact is larger than 20 MiB");
    }

    /** The media type without parameters such as charset; a missing or unparsable header stays empty and the use case answers 415. */
    private static String baseMediaType(String contentType) {
        if (contentType == null) {
            return "";
        }
        try {
            MediaType type = MediaType.parseMediaType(contentType);
            return type.getType() + "/" + type.getSubtype();
        } catch (IllegalArgumentException e) {
            return "";
        }
    }
}
