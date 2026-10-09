package com.quancrypt.core.usecase;

import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.SourceFile;
import com.quancrypt.core.port.outbound.IdGenerator;
import com.quancrypt.core.port.outbound.SourceFileReader;
import com.quancrypt.core.port.outbound.SourceFileWriter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Finds or creates the source files a request mentions; a file has exactly one kind (D-140, D-146). */
public final class SourceFileResolver {

    private final SourceFileReader reader;
    private final SourceFileWriter writer;
    private final IdGenerator ids;

    public SourceFileResolver(SourceFileReader reader, SourceFileWriter writer, IdGenerator ids) {
        this.reader = reader;
        this.writer = writer;
        this.ids = ids;
    }

    /** Same path with two different kinds in one request is a validation failure. */
    static Map<String, LocationKind> kindsByPath(List<PathKind> wanted) {
        Map<String, LocationKind> kinds = new LinkedHashMap<>();
        for (PathKind pk : wanted) {
            LocationKind previous = kinds.putIfAbsent(pk.path(), pk.kind());
            if (previous != null && previous != pk.kind()) {
                throw Fail.validation("a file has one kind, but " + pk.path() + " is given two");
            }
        }
        return kinds;
    }

    Map<String, SourceFile> resolve(UUID scanId, Map<String, LocationKind> wanted) {
        Map<String, SourceFile> found = new HashMap<>(reader.byPaths(scanId, wanted.keySet()));
        List<SourceFile> created = new ArrayList<>();
        for (Map.Entry<String, LocationKind> entry : wanted.entrySet()) {
            SourceFile existing = found.get(entry.getKey());
            if (existing == null) {
                SourceFile file = Guard.valid(() -> new SourceFile(ids.next(), scanId, entry.getKey(), entry.getValue()));
                created.add(file);
                found.put(file.path(), file);
            } else if (existing.locationKind() != entry.getValue()) {
                throw Fail.validation("a file has one kind, but " + entry.getKey() + " is already recorded as " + existing.locationKind());
            }
        }
        if (!created.isEmpty()) {
            writer.insertAll(created);
        }
        return found;
    }
}
