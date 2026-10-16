package com.quancrypt.analyzer.evaluation;

import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * The repository root as the QBank golden test sees it (D-209): the root {@code docker-compose.yml} and the files of
 * {@code reference-system/}, nothing else, so the other services of the repository do not show up in the topology. The
 * reference system is read through the real file system tree (listing the whole repository would take minutes on a mounted
 * Windows drive); the compose file is read directly. Evaluation and test code only.
 */
public final class RepositoryView implements SourceTree {

    private static final String COMPOSE = "docker-compose.yml";
    private static final String PREFIX = "reference-system/";

    private final AnalysisRoot root;
    private final SourceTree reference;
    private final Path composeFile;

    public RepositoryView(AnalysisRoot root, SourceTree reference, Path composeFile) {
        this.root = root;
        this.reference = reference;
        this.composeFile = composeFile;
    }

    @Override
    public AnalysisRoot root() {
        return root;
    }

    @Override
    public List<RelativePath> files() {
        List<RelativePath> files = new ArrayList<>();
        files.add(RelativePath.of(COMPOSE));
        reference.files().forEach(f -> files.add(RelativePath.of(PREFIX + f.value())));
        files.sort((a, b) -> a.value().compareTo(b.value()));
        return files;
    }

    @Override
    public boolean exists(RelativePath path) {
        return path.value().equals(COMPOSE) ? Files.isRegularFile(composeFile) : path.value().startsWith(PREFIX) && reference.exists(inner(path));
    }

    @Override
    public byte[] read(RelativePath path) {
        if (path.value().equals(COMPOSE)) {
            try {
                return Files.readAllBytes(composeFile);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
        return reference.read(inner(path));
    }

    @Override
    public List<String> readLines(RelativePath path) {
        return new String(read(path), StandardCharsets.UTF_8).lines().toList();
    }

    @Override
    public void checkpoint() {
        reference.checkpoint();
    }

    private static RelativePath inner(RelativePath path) {
        if (!path.value().startsWith(PREFIX)) {
            throw new SourceNotFoundException("not part of the view");
        }
        return RelativePath.of(path.value().substring(PREFIX.length()));
    }
}
