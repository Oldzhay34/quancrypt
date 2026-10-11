package com.quancrypt.analyzer.infrastructure.filesystem;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

/**
 * Opens a directory of the local file system read-only. The root must be a real directory whose canonical path equals
 * the given path, so a root that is or passes through a symbolic link is refused.
 */
public final class FileSystemSourceTreeReader implements SourceTreeReader {

    /** 5 MiB per file (D-178i). */
    public static final long DEFAULT_MAX_FILE_BYTES = 5L * 1024 * 1024;
    public static final int DEFAULT_MAX_FILES = 200_000;

    private final long maxFileBytes;
    private final int maxFiles;

    public FileSystemSourceTreeReader() {
        this(DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_FILES);
    }

    public FileSystemSourceTreeReader(long maxFileBytes, int maxFiles) {
        if (maxFileBytes < 1 || maxFileBytes > Integer.MAX_VALUE - 1 || maxFiles < 1) {
            throw new IllegalArgumentException("the reading limits must be positive");
        }
        this.maxFileBytes = maxFileBytes;
        this.maxFiles = maxFiles;
    }

    @Override
    public SourceTree open(AnalysisRoot root) {
        Path given = Path.of(root.value());
        if (!Files.isDirectory(given, LinkOption.NOFOLLOW_LINKS)) {
            throw new PathNotAllowedException("the root is not a directory");
        }
        Path real;
        try {
            real = given.toRealPath();
        } catch (IOException e) {
            throw new PathNotAllowedException("the root cannot be resolved");
        }
        if (!real.equals(given.toAbsolutePath().normalize())) {
            throw new PathNotAllowedException("the root passes through a symbolic link");
        }
        return new FileSystemSourceTree(root, real, maxFileBytes, maxFiles);
    }
}
