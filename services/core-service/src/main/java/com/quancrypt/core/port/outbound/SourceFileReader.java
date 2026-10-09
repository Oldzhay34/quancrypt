package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.SourceFile;
import java.util.Collection;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/** Reads source files of a scan. */
public interface SourceFileReader {

    Map<String, SourceFile> byPaths(UUID scanId, Collection<String> paths);

    Optional<SourceFile> find(UUID sourceFileId);

    Map<UUID, SourceFile> byIds(Collection<UUID> sourceFileIds);
}
