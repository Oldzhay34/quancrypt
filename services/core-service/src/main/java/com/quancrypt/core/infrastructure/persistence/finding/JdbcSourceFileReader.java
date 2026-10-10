package com.quancrypt.core.infrastructure.persistence.finding;

import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.SourceFileReader;
import java.util.Collection;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads source files of a scan in bulk (one query per call, no N+1). */
public final class JdbcSourceFileReader implements SourceFileReader {

    private final JdbcClient jdbc;

    public JdbcSourceFileReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Map<String, SourceFile> byPaths(UUID scanId, Collection<String> paths) {
        if (paths.isEmpty()) {
            return Map.of();
        }
        return jdbc.sql("SELECT " + FindingRows.SOURCE_FILE_COLUMNS + " FROM source_file WHERE scan_id = :scanId AND path = ANY(CAST(:paths AS text[]))")
                .param("scanId", scanId).param("paths", Sql.textArray(paths)).query(FindingRows::sourceFile).list().stream()
                .collect(Collectors.toMap(SourceFile::path, Function.identity()));
    }

    @Override
    public Optional<SourceFile> find(UUID sourceFileId) {
        return jdbc.sql("SELECT " + FindingRows.SOURCE_FILE_COLUMNS + " FROM source_file WHERE id = :id")
                .param("id", sourceFileId).query(FindingRows::sourceFile).optional();
    }

    @Override
    public Map<UUID, SourceFile> byIds(Collection<UUID> sourceFileIds) {
        if (sourceFileIds.isEmpty()) {
            return Map.of();
        }
        return jdbc.sql("SELECT " + FindingRows.SOURCE_FILE_COLUMNS + " FROM source_file WHERE id = ANY(CAST(:ids AS uuid[]))")
                .param("ids", Sql.textArray(sourceFileIds)).query(FindingRows::sourceFile).list().stream()
                .collect(Collectors.toMap(SourceFile::id, Function.identity()));
    }
}
