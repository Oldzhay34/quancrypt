package com.quancrypt.analyzer.port.outbound;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;

/** Opens a project directory for reading. */
public interface SourceTreeReader {

    /**
     * The source tree of the root.
     *
     * @throws com.quancrypt.analyzer.domain.exception.PathNotAllowedException when the root is not a directory, cannot be
     *     resolved or passes through a symbolic link
     */
    SourceTree open(AnalysisRoot root);
}
