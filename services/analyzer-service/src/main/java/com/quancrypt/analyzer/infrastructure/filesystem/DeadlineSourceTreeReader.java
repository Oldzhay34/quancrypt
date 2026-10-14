package com.quancrypt.analyzer.infrastructure.filesystem;

import com.quancrypt.analyzer.domain.exception.AnalysisTimeoutException;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.port.outbound.Clock;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

/**
 * Gives every opened tree a deadline (D-199): once the time budget is spent, the next listing or read fails with
 * {@link AnalysisTimeoutException}. The plugin also calls {@link SourceTree#checkpoint()} before every file, so a running
 * analysis ends within one file of its budget; no other plugin port changes for this.
 */
public final class DeadlineSourceTreeReader implements SourceTreeReader {

    private final SourceTreeReader delegate;
    private final Clock clock;
    private final Duration budget;

    public DeadlineSourceTreeReader(SourceTreeReader delegate, Clock clock, Duration budget) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.budget = Objects.requireNonNull(budget, "budget");
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("the time budget must be positive");
        }
    }

    @Override
    public SourceTree open(AnalysisRoot root) {
        return new DeadlineTree(delegate.open(root), clock, clock.now().plus(budget));
    }

    private record DeadlineTree(SourceTree tree, Clock clock, Instant deadline) implements SourceTree {

        private void check() {
            if (clock.now().isAfter(deadline)) {
                throw new AnalysisTimeoutException("the analysis ran past its time budget");
            }
        }

        @Override
        public void checkpoint() {
            check();
        }

        @Override
        public AnalysisRoot root() {
            return tree.root();
        }

        @Override
        public List<RelativePath> files() {
            check();
            return tree.files();
        }

        @Override
        public boolean exists(RelativePath path) {
            check();
            return tree.exists(path);
        }

        @Override
        public byte[] read(RelativePath path) {
            check();
            return tree.read(path);
        }

        @Override
        public List<String> readLines(RelativePath path) {
            check();
            return tree.readLines(path);
        }
    }
}
