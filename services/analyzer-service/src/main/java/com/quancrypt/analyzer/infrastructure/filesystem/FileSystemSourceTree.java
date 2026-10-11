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

    FileSystemSourceTree(AnalysisRoot root, Path base, long maxFileBytes, int maxFiles) {
        this.root = root;
        this.base = base;
        this.maxFileBytes = maxFileBytes;
        this.maxFiles = maxFiles;
    }

    @Override
    public AnalysisRoot root() {
        return root;
    }

    @Override
    public List<RelativePath> files() {
        List<RelativePath> found = new ArrayList<>();
        try {
            // No FOLLOW_LINKS: a link is visited as a link and never entered or listed.
            Files.walkFileTree(base, EnumSet.noneOf(FileVisitOption.class), Integer.MAX_VALUE, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) {
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

    @Override
    public boolean exists(RelativePath path) {
        return Files.isRegularFile(resolve(path), LinkOption.NOFOLLOW_LINKS);
    }

    @Override
    public byte[] read(RelativePath path) {
        Path file = resolve(path);
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

    private Path resolve(RelativePath path) {
        Path current = base;
        for (String segment : path.segments()) {
            current = current.resolve(segment);
            if (Files.isSymbolicLink(current)) {
                throw new PathNotAllowedException("the path passes through a symbolic link");
            }
        }
        if (!current.normalize().startsWith(base)) {
            throw new PathNotAllowedException("the path leaves the root");
        }
        return current;
    }
}
