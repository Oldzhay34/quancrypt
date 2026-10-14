package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.quancrypt.analyzer.domain.model.CryptoUsage;
import java.util.List;

/**
 * The full result of one analysis: the usages (what {@code LanguagePlugin.analyzeCrypto} returns), the crypto libraries
 * found in build files and the diagnostics. P3.3 does not hand the library facts and the diagnostics to the callers (D-204i):
 * the contract has no field for them, and adding one is a contract change for a later phase (ILERIDE, Faz 3 / P3.3), so
 * both reach the evaluation only.
 */
public record AnalysisOutcome(List<CryptoUsage> usages, List<LibraryDependency> libraries, Diagnostics diagnostics) {

    public AnalysisOutcome {
        usages = List.copyOf(usages);
        libraries = List.copyOf(libraries);
    }
}
