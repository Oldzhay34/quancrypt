package com.quancrypt.analyzer.evaluation;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.infrastructure.filesystem.FileSystemSourceTreeReader;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.AnalysisOutcome;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugin;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Runs the plugin over the QBank reference system and compares it with the golden inventory. */
public final class QbankEvaluation {

    /** The golden entries a Java plugin is expected to find: all except Python code (D-184). */
    public static boolean javaPluginScope(GoldenEntry entry) {
        return !entry.file().endsWith(".py");
    }

    /** The outcome of the analysis together with its comparison. */
    public record Run(AnalysisOutcome outcome, GoldenComparison.Result comparison) {
    }

    private QbankEvaluation() {
    }

    public static Run run(JavaSpringPlugin plugin, Path referenceSystem, Path expectedDirectory) throws IOException {
        Path certificates = referenceSystem.resolve("certs/out");
        if (!Files.isDirectory(certificates)) {
            throw new IllegalStateException("reference-system/certs/out is missing: run 'bash certs/generate.sh' in reference-system first "
                    + "(the golden inventory expects the generated certificates and keys)");
        }
        AnalysisRoot root = new AnalysisRoot(referenceSystem.toRealPath().toString());
        AnalysisOutcome outcome = plugin.analyze(new FileSystemSourceTreeReader().open(root));
        var golden = GoldenInventory.load(expectedDirectory.resolve("crypto_inventory.yaml"));
        return new Run(outcome, GoldenComparison.compare(golden, outcome.usages(), QbankEvaluation::javaPluginScope));
    }
}
