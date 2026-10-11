package com.quancrypt.analyzer.domain.model;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import java.util.List;

/** The directories an analysis root may lie in: {@code /workspace} and {@code /corpus} in the container (P3.1). */
public record AllowedRoots(List<String> directories) {

    public static final AllowedRoots DEFAULT = new AllowedRoots(List.of("/workspace", "/corpus"));

    public AllowedRoots {
        directories = List.copyOf(directories);
        if (directories.isEmpty()) {
            throw new IllegalArgumentException("at least one allowed directory is needed");
        }
        for (String directory : directories) {
            if (!AnalysisRoot.isCanonicalAbsolute(directory)) {
                throw new IllegalArgumentException("an allowed directory must be a canonical absolute path below /");
            }
        }
    }

    /** The root, when it is canonical and at or below an allowed directory. */
    public AnalysisRoot admit(String path) {
        if (path == null) {
            throw new PathNotAllowedException("the root is missing");
        }
        AnalysisRoot root = new AnalysisRoot(path);
        for (String directory : directories) {
            if (root.isAtOrBelow(directory)) {
                return root;
            }
        }
        throw new PathNotAllowedException("the root is outside the allowed directories");
    }
}
