package com.quancrypt.core.facade.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;

/** Link of a topology (schema LinkInput). */
public record LinkInputDto(@NotBlank @Size(max = 200) String source, @NotBlank @Size(max = 200) String target, @NotNull String protocol, @NotNull Boolean tls, @NotNull Boolean mtls, @NotNull @Size(max = 100) List<@NotNull @Valid CallSiteInputDto> callSites, @NotNull @Size(max = 500) List<@NotNull UUID> findingIds) {

    public LinkInputDto {
        callSites = callSites == null ? null : List.copyOf(callSites);
        findingIds = findingIds == null ? null : List.copyOf(findingIds);
    }
}

