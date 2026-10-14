package com.quancrypt.analyzer.infrastructure.plugin.javaspring.config;

import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.Optional;

/** One flattened configuration property with the line it starts on and the profile of its document, if any. */
public record ConfigProperty(RelativePath file, String key, String value, int line, Optional<String> profile) {
}
