package com.quancrypt.analyzer.contract;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;

/** The test double keeps the port's contract, so use case tests built on it are meaningful. */
class InMemorySourceTreeReaderContractTest extends SourceTreeReaderContract {

    private static final String ROOT = "/workspace/project";

    @Override
    protected Fixture newFixture() {
        InMemorySourceTreeReader reader = new InMemorySourceTreeReader(LIMIT).directory(ROOT);
        return new Fixture() {
            @Override
            public SourceTreeReader reader() {
                return reader;
            }

            @Override
            public AnalysisRoot root() {
                return new AnalysisRoot(ROOT);
            }

            @Override
            public void file(String path, byte[] content) {
                reader.file(ROOT, path, content);
            }

            @Override
            public void linkToOutsideFile(String path) {
                reader.file(ROOT, path, "outside").link(ROOT, path);
            }

            @Override
            public void linkToOutsideDirectory(String path) {
                reader.file(ROOT, path + "/secret.txt", "secret").link(ROOT, path);
            }

            @Override
            public void linkInside(String path, String target) {
                reader.file(ROOT, path, "alias").link(ROOT, path);
            }

            @Override
            public AnalysisRoot linkedRoot() {
                reader.directory("/workspace/linked").linkedRoot("/workspace/linked");
                return new AnalysisRoot("/workspace/linked");
            }

            @Override
            public AnalysisRoot missingRoot() {
                return new AnalysisRoot("/workspace/missing");
            }

            @Override
            public SourceTreeReader readerWithTotalBudget(long bytes) {
                return reader.withTotalBudget(bytes);
            }
        };
    }
}
