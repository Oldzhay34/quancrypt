package com.quancrypt.analyzer.port.inbound;

import java.util.List;

/** Lists the installed language plugins. Failures are {@link AnalyzerUseCaseException}s. */
public interface ListPluginsUseCase {

    List<PluginView> list();
}
