package com.quancrypt.analyzer.fake;

import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.exception.SourceTooLargeException;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * Test double of the source tree reader: directories of files kept in memory, with symbolic links marked by path. It
 * keeps the port's contract (SourceTreeReaderContract) so use case tests can rely on it.
 */
public final class InMemorySourceTreeReader implements SourceTreeReader {

    private final long maxFileBytes;
    private final long maxTotalBytes;
    private final Map<String, Map<String, byte[]>> roots = new HashMap<>();
    private final Map<String, Set<String>> links = new HashMap<>();
    private final Set<String> linkedRoots = new HashSet<>();

    public InMemorySourceTreeReader() {
        this(5L * 1024 * 1024);
    }

    public InMemorySourceTreeReader(long maxFileBytes) {
        this(maxFileBytes, Long.MAX_VALUE);
    }

    public InMemorySourceTreeReader(long maxFileBytes, long maxTotalBytes) {
        this.maxFileBytes = maxFileBytes;
        this.maxTotalBytes = maxTotalBytes;
    }

    /** A reader over the same directories that stops handing out bytes after {@code bytes} per opened tree. */
    public InMemorySourceTreeReader withTotalBudget(long bytes) {
        InMemorySourceTreeReader copy = new InMemorySourceTreeReader(maxFileBytes, bytes);
        copy.roots.putAll(roots);
        copy.links.putAll(links);
        copy.linkedRoots.addAll(linkedRoots);
        return copy;
    }

    public InMemorySourceTreeReader directory(String root) {
        roots.computeIfAbsent(root, r -> new TreeMap<>());
        links.computeIfAbsent(root, r -> new HashSet<>());
        return this;
    }

    public InMemorySourceTreeReader file(String root, String path, String content) {
        return file(root, path, content.getBytes(StandardCharsets.UTF_8));
    }

    public InMemorySourceTreeReader file(String root, String path, byte[] content) {
        directory(root).roots.get(root).put(path, content.clone());
        return this;
    }

    /** Marks a path below the root as a symbolic link (to a file or a directory, inside or outside the root). */
    public InMemorySourceTreeReader link(String root, String path) {
        directory(root).links.get(root).add(path);
        return this;
    }

    /** Marks the root itself as a symbolic link. */
    public InMemorySourceTreeReader linkedRoot(String root) {
        linkedRoots.add(root);
        return this;
    }

    @Override
    public SourceTree open(AnalysisRoot root) {
        if (linkedRoots.contains(root.value())) {
            throw new PathNotAllowedException("the root passes through a symbolic link");
        }
        Map<String, byte[]> files = roots.get(root.value());
        if (files == null) {
            throw new PathNotAllowedException("the root is not a directory");
        }
        return new Tree(root, files, links.get(root.value()));
    }

    private final class Tree implements SourceTree {

        private final AnalysisRoot root;
        private final Map<String, byte[]> files;
        private final Set<String> linkPaths;
        private long totalBytes;

        Tree(AnalysisRoot root, Map<String, byte[]> files, Set<String> linkPaths) {
            this.root = root;
            this.files = files;
            this.linkPaths = linkPaths;
        }

        @Override
        public AnalysisRoot root() {
            return root;
        }

        @Override
        public List<RelativePath> files() {
            List<RelativePath> listed = new ArrayList<>();
            for (String path : files.keySet()) {
                if (!throughLink(path)) {
                    listed.add(RelativePath.of(path));
                }
            }
            return List.copyOf(listed);
        }

        @Override
        public boolean exists(RelativePath path) {
            refuseLinks(path);
            return files.containsKey(path.value());
        }

        @Override
        public byte[] read(RelativePath path) {
            refuseLinks(path);
            byte[] content = files.get(path.value());
            if (content == null) {
                throw new SourceNotFoundException("the file does not exist");
            }
            if (content.length > maxFileBytes) {
                throw new SourceTooLargeException("the file is larger than the reading limit");
            }
            totalBytes += content.length;
            if (totalBytes > maxTotalBytes) {
                throw new SourceTooLargeException("the project is larger than the reading limit");
            }
            return content.clone();
        }

        @Override
        public List<String> readLines(RelativePath path) {
            String text = new String(read(path), StandardCharsets.UTF_8);
            if (text.isEmpty()) {
                return List.of();
            }
            List<String> lines = new ArrayList<>(List.of(text.split("\n", -1)));
            if (text.endsWith("\n")) {
                lines.removeLast();
            }
            return lines.stream().map(l -> l.endsWith("\r") ? l.substring(0, l.length() - 1) : l).toList();
        }

        private void refuseLinks(RelativePath path) {
            if (throughLink(path.value())) {
                throw new PathNotAllowedException("the path passes through a symbolic link");
            }
        }

        private boolean throughLink(String path) {
            StringBuilder prefix = new StringBuilder();
            for (String segment : path.split("/")) {
                if (!prefix.isEmpty()) {
                    prefix.append('/');
                }
                prefix.append(segment);
                if (linkPaths.contains(prefix.toString())) {
                    return true;
                }
            }
            return false;
        }
    }
}
