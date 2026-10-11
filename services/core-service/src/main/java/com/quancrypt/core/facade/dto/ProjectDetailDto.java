package com.quancrypt.core.facade.dto;

/** Project with its current runtime profile (schema ProjectDetail). */
public record ProjectDetailDto(ProjectDto project, RuntimeProfileDto currentRuntimeProfile) {
}
