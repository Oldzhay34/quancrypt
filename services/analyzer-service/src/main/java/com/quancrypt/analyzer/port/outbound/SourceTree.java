package com.quancrypt.analyzer.port.outbound;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import java.util.List;

/**
 * Read-only access to the files below one root. Symbolic links are never followed: they are not listed, and a path that
 * is or passes through one is refused. Implementations never write.
 */
public interface SourceTree {

    AnalysisRoot root();

    /**
     * Every regular file below the root, sorted by path.
     *
     * @throws com.quancrypt.analyzer.domain.exception.SourceTooLargeException when the tree has more files than the limit
     */
    List<RelativePath> files();

    /**
     * Whether a regular file exists at the path.
     *
     * @throws com.quancrypt.analyzer.domain.exception.PathNotAllowedException when the path is or passes through a symbolic link
     */
    boolean exists(RelativePath path);

    /**
     * The bytes of a regular file.
     *
     * @throws com.quancrypt.analyzer.domain.exception.PathNotAllowedException when the path is or passes through a symbolic link
     * @throws com.quancrypt.analyzer.domain.exception.SourceNotFoundException when there is no regular file at the path
     * @throws com.quancrypt.analyzer.domain.exception.SourceTooLargeException when the file is larger than the limit
     */
    byte[] read(RelativePath path);

    /**
     * The lines of a text file, decoded as UTF-8 (malformed bytes replaced), without line terminators. Same failures as
     * {@link #read(RelativePath)}.
     */
    List<String> readLines(RelativePath path);

    /**
     * A point where a long analysis may be stopped (D-199): a tree with a time budget throws
     * {@link com.quancrypt.analyzer.domain.exception.AnalysisTimeoutException} once the budget is spent; any other tree does
     * nothing. A plugin calls it before every file, so a run does not outlast its budget by more than one file.
     */
    default void checkpoint() {
    }
}
