package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.UsageContext;
import java.util.Optional;

/** Optional filters of a finding listing. */
public record FindingFilter(
        Optional<Priority> priority,
        Optional<AlgorithmFamily> algorithmFamily,
        Optional<UsageContext> usageContext,
        Optional<LocationKind> locationKind,
        Optional<ClassifiedBy> classifiedBy) {
}
