package com.quancrypt.core.facade.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

/** Optional body of RelayOutboxEvents (schema RelayRequest). */
public record RelayRequestInput(@Min(1) @Max(200) Integer batchSize) {
}
