package com.quancrypt.analyzer.contract;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.infrastructure.filesystem.FileSystemSourceTreeReader;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import org.junit.jupiter.api.io.TempDir;

/** The file system adapter against real directories and real symbolic links (POSIX; the build runs in WSL). */
class FileSystemSourceTreeReaderContractTest extends SourceTreeReaderContract {

    @TempDir
    Path temp;

    @Override
    protected Fixture newFixture() {
        Path base = canonical(temp);
        Path project = mkdirs(base.resolve("project"));
        Path outside = mkdirs(base.resolve("outside"));
        write(outside.resolve("leak.txt"), "outside".getBytes(StandardCharsets.UTF_8));
        write(outside.resolve("dir/secret.txt"), "secret".getBytes(StandardCharsets.UTF_8));
        SourceTreeReader reader = new FileSystemSourceTreeReader(LIMIT, 1000);
        return new Fixture() {
            @Override
            public SourceTreeReader reader() {
                return reader;
            }

            @Override
            public AnalysisRoot root() {
                return new AnalysisRoot(project.toString());
            }

            @Override
            public void file(String path, byte[] content) {
                write(project.resolve(path), content);
            }

            @Override
            public void linkToOutsideFile(String path) {
                link(project.resolve(path), outside.resolve("leak.txt"));
            }

            @Override
            public void linkToOutsideDirectory(String path) {
                link(project.resolve(path), outside.resolve("dir"));
            }

            @Override
            public void linkInside(String path, String target) {
                link(project.resolve(path), project.resolve(target));
            }

            @Override
            public AnalysisRoot linkedRoot() {
                Path linked = base.resolve("linked-project");
                link(linked, project);
                return new AnalysisRoot(linked.toString());
            }

            @Override
            public AnalysisRoot missingRoot() {
                return new AnalysisRoot(base.resolve("missing").toString());
            }

            @Override
            public SourceTreeReader readerWithTotalBudget(long bytes) {
                return new FileSystemSourceTreeReader(LIMIT, 1000, 1000, 64, bytes);
            }
        };
    }

    private static Path canonical(Path path) {
        try {
            return path.toRealPath();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static Path mkdirs(Path dir) {
        try {
            return Files.createDirectories(dir);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void write(Path file, byte[] content) {
        try {
            Files.createDirectories(Objects.requireNonNull(file.getParent(), "parent"));
            Files.write(file, content);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void link(Path link, Path target) {
        try {
            Files.createDirectories(Objects.requireNonNull(link.getParent(), "parent"));
            Files.createSymbolicLink(link, target);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
