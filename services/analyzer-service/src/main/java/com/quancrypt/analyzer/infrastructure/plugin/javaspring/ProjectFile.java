package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.LocationKind;
import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.List;

/** A file of the analyzed project with its kind and the location kind its findings carry. */
public record ProjectFile(RelativePath path, FileKind kind, LocationKind location) {

    public String name() {
        List<String> segments = path.segments();
        return segments.get(segments.size() - 1);
    }
}
