package com.quancrypt.analyzer.infrastructure.filesystem;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * A read-only view of one canonical root directory. Every path is resolved segment by segment and refused when a
 * segment is a symbolic link; files are opened with NOFOLLOW_LINKS, which protects the last segment only. A directory
 * swapped for a link between the check and the open is not caught (the mount is read-only, so this needs a concurrent
 * writer on the host; see ILERIDE).
 */
final class FileSystemSourceTree implements SourceTree {

    private final AnalysisRoot root;
    private final Path base;
    private final long maxFileBytes;
    private final int maxFiles;
    private final int maxEntries;
    private final int maxDepth;
    private final long maxTotalBytes;
    private final AtomicLong totalBytes = new AtomicLong();
    private final Set<Path> verifiedDirectories = ConcurrentHashMap.newKeySet();
    private List<RelativePath> listing;

    FileSystemSourceTree(AnalysisRoot root, Path base, long maxFileBytes, int maxFiles, int maxEntries, int maxDepth, long maxTotalBytes) {
        this.root = root;
        this.base = base;
        this.maxFileBytes = maxFileBytes;
        this.maxFiles = maxFiles;
        this.maxEntries = maxEntries;
        this.maxDepth = maxDepth;
        this.maxTotalBytes = maxTotalBytes;
    }

    @Override
    public AnalysisRoot root() {
        return root;
    }

    /**
     * The files of the tree, listed once: a tree is the view of one analysis, which asks for the list three times (the
     * detectors, the runtime versions, the statistics), and on a slow disk (WSL's /mnt/c) every walk of a project with
     * 90,000 entries is minutes (P3.3 measurement, D-205). A file created while the analysis runs is not listed.
     */
    @Override
    public synchronized List<RelativePath> files() {
        if (listing == null) {
            listing = walk();
        }
        return List.copyOf(listing);
    }

    private List<RelativePath> walk() {
        List<RelativePath> found = new ArrayList<>();
        try {
            // No FOLLOW_LINKS: a link is visited as a link and never entered or listed.
            int[] visited = new int[1];
            Files.walkFileTree(base, EnumSet.noneOf(FileVisitOption.class), maxDepth, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(Path directory, BasicFileAttributes attributes) {
                    count(visited);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) {
                    count(visited);
                    if (attributes.isDirectory()) {
                        throw new SourceTooLargeException("the project is nested deeper than the reading limit");
                    }
                    if (attributes.isRegularFile()) {
                        addIfValid(found, file);
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFileFailed(Path file, IOException failure) {
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException e) {
            throw new UncheckedIOException("the source tree cannot be listed", e);
        }
        found.sort(Comparator.comparing(RelativePath::value));
        return List.copyOf(found);
    }

    private void count(int[] visited) {
        if (++visited[0] > maxEntries) {
            throw new SourceTooLargeException("the project has more entries than the reading limit");
        }
    }

    @Override
    public boolean exists(RelativePath path) {
        return Files.isRegularFile(resolve(path, true), LinkOption.NOFOLLOW_LINKS);
    }

    @Override
    public byte[] read(RelativePath path) {
        // The attributes below are read without following links, so a link as the last segment is refused there.
        Path file = resolve(path, false);
        BasicFileAttributes attributes;
        try {
            attributes = Files.readAttributes(file, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        } catch (IOException e) {
            throw new SourceNotFoundException("the file does not exist");
        }
        if (attributes.isSymbolicLink()) {
            throw new PathNotAllowedException("the path is a symbolic link");
        }
        if (!attributes.isRegularFile()) {
            throw new SourceNotFoundException("the path is not a regular file");
        }
        if (attributes.size() > maxFileBytes) {
            throw new SourceTooLargeException("the file is larger than the reading limit");
        }
        try (InputStream in = Files.newInputStream(file, LinkOption.NOFOLLOW_LINKS)) {
            byte[] content = in.readNBytes((int) maxFileBytes + 1);
            if (content.length > maxFileBytes) {
                throw new SourceTooLargeException("the file is larger than the reading limit");
            }
            if (totalBytes.addAndGet(content.length) > maxTotalBytes) {
                throw new SourceTooLargeException("the project is larger than the reading limit");
            }
            return content;
        } catch (NoSuchFileException e) {
            throw new SourceNotFoundException("the file does not exist");
        } catch (IOException e) {
            throw new UncheckedIOException("the file cannot be read", e);
        }
    }

    @Override
    public List<String> readLines(RelativePath path) {
        return lines(read(path));
    }

    static List<String> lines(byte[] content) {
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPLACE)
                    .onUnmappableCharacter(CodingErrorAction.REPLACE)
                    .decode(ByteBuffer.wrap(content))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new IllegalStateException("a replacing decoder does not fail", e);
        }
        if (text.isEmpty()) {
            return List.of();
        }
        List<String> lines = new ArrayList<>(Arrays.asList(text.split("\n", -1)));
        if (text.endsWith("\n")) {
            lines.removeLast();
        }
        return lines.stream().map(line -> line.endsWith("\r") ? line.substring(0, line.length() - 1) : line).toList();
    }

    private void addIfValid(List<RelativePath> found, Path file) {
        StringBuilder relative = new StringBuilder();
        for (Path name : base.relativize(file)) {
            if (!relative.isEmpty()) {
                relative.append('/');
            }
            relative.append(name);
        }
        try {
            found.add(RelativePath.of(relative.toString()));
        } catch (PathNotAllowedException e) {
            return; // a name the contract cannot carry (a control character, say) is not listed
        }
        if (found.size() > maxFiles) {
            throw new SourceTooLargeException("the project has more files than the reading limit");
        }
    }

    /**
     * The file system path of a relative path, refusing any symbolic link on the way. A directory that has been checked once
     * is not checked again for this tree: a project has few directories and many files, and one {@code lstat} per path
     * segment and per file made a 5,000 file project take minutes on a slow disk (WSL's /mnt/c, a bind mounted Windows
     * folder; P3.3 measurement, D-205). The last segment is checked here only when the caller does not check it itself.
     */
    private Path resolve(RelativePath path, boolean checkLastSegment) {
        Path current = base;
        List<String> segments = path.segments();
        for (int i = 0; i < segments.size(); i++) {
            current = current.resolve(segments.get(i));
            boolean last = i == segments.size() - 1;
            if (last) {
                if (checkLastSegment && Files.isSymbolicLink(current)) {
                    throw new PathNotAllowedException("the path passes through a symbolic link");
                }
            } else if (!verifiedDirectories.contains(current)) {
                if (Files.isSymbolicLink(current)) {
                    throw new PathNotAllowedException("the path passes through a symbolic link");
                }
                verifiedDirectories.add(current);
            }
        }
        if (!current.normalize().startsWith(base)) {
            throw new PathNotAllowedException("the path leaves the root");
        }
        return current;
    }
}
