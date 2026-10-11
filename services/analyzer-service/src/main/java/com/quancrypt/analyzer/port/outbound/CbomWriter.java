package com.quancrypt.analyzer.port.outbound;

import com.quancrypt.analyzer.domain.model.Cbom;
import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import java.util.List;

/** Writes the CycloneDX CBOM of an analysis (implementation in P3.3). */
public interface CbomWriter {

    Cbom write(ProjectDescriptor project, List<CryptoUsage> usages);
}
