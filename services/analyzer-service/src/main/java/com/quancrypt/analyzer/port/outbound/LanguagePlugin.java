package com.quancrypt.analyzer.port.outbound;

import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.PluginInfo;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import java.util.List;

/**
 * Language specific analysis behind one interface (NFR-06). A new language is a new implementation; the use cases pick
 * the first plugin of the list that supports the project (OCP).
 */
public interface LanguagePlugin {

    /** The plugin's id, name, version and project types (GET /api/v1/plugins). */
    PluginInfo info();

    boolean supports(ProjectDescriptor project);

    List<CryptoUsage> analyzeCrypto(SourceTree tree);

    ServiceGraph buildTopology(SourceTree tree);

    RuntimeInfo runtimeInfo(SourceTree tree);
}
