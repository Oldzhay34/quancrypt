package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.exception.UnsupportedProjectException;
import com.quancrypt.analyzer.domain.model.AnalysisStats;
import com.quancrypt.analyzer.domain.model.Cbom;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.port.inbound.AnalysisView;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoCommand;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoUseCase;
import com.quancrypt.analyzer.port.outbound.CbomWriter;
import com.quancrypt.analyzer.port.outbound.Clock;
import com.quancrypt.analyzer.port.outbound.IdGenerator;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

/**
 * Analyzes a project with the plugin that supports it: findings (test code kept and marked unless the caller excludes
 * it, D-173), runtime versions, CBOM and counters. One analysis returns at most 5000 findings (D-178b).
 */
public final class AnalyzeCryptoService implements AnalyzeCryptoUseCase {

    public static final int MAX_FINDINGS = 5000;

    private final ProjectOpener opener;
    private final PluginSelector plugins;
    private final CbomWriter cbomWriter;
    private final IdGenerator ids;
    private final Clock clock;

    public AnalyzeCryptoService(ProjectOpener opener, PluginSelector plugins, CbomWriter cbomWriter, IdGenerator ids, Clock clock) {
        this.opener = Objects.requireNonNull(opener, "opener");
        this.plugins = Objects.requireNonNull(plugins, "plugins");
        this.cbomWriter = Objects.requireNonNull(cbomWriter, "cbomWriter");
        this.ids = Objects.requireNonNull(ids, "ids");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    @Override
    public AnalysisView analyze(AnalyzeCryptoCommand command) {
        Instant started = clock.now();
        OpenedProject project = opener.open(command.root());
        return Failures.translate(() -> {
            LanguagePlugin plugin = plugins.select(project.descriptor());
            List<CryptoUsage> usages = plugin.analyzeCrypto(project.tree()).stream()
                    .filter(usage -> command.includeTests() || !usage.inTestCode())
                    .toList();
            if (usages.size() > MAX_FINDINGS) {
                throw new UnsupportedProjectException("the project has more findings than one analysis can return");
            }
            RuntimeInfo runtime = plugin.runtimeInfo(project.tree());
            Cbom cbom = cbomWriter.write(project.descriptor(), usages);
            long durationMs = Math.max(0, Duration.between(started, clock.now()).toMillis());
            AnalysisStats stats = new AnalysisStats(project.tree().files().size(), usages.size(), durationMs);
            return Views.analysis(ids.newId(), project.descriptor(), runtime, usages, cbom, stats);
        });
    }
}
