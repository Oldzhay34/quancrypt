package com.quancrypt.analyzer.api.dto;

import com.fasterxml.jackson.annotation.JsonRawValue;
import com.quancrypt.analyzer.facade.dto.AnalysisDto;
import java.util.List;
import java.util.UUID;

/**
 * The body of AnalyzeCrypto. The CBOM is a JSON document already; {@code @JsonRawValue} writes it as the object it is
 * instead of as an escaped string (the contract's `cbom` is an object).
 */
public record AnalysisResponse(UUID analysisId, String projectType, AnalysisDto.RuntimeDto runtime,
        List<AnalysisDto.FindingDto> findings, @JsonRawValue String cbom, AnalysisDto.StatsDto stats) {

    public AnalysisResponse {
        findings = List.copyOf(findings);
    }

    public static AnalysisResponse of(AnalysisDto dto) {
        return new AnalysisResponse(dto.analysisId(), dto.projectType(), dto.runtime(), dto.findings(), dto.cbom(), dto.stats());
    }
}
