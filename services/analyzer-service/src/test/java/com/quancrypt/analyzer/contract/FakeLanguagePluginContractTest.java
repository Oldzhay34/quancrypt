package com.quancrypt.analyzer.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.fake.FakePlugin;
import com.quancrypt.analyzer.fake.InMemorySourceTreeReader;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import org.junit.jupiter.api.Test;

/** The test double keeps the plugin contract, so use case tests built on it are meaningful. */
class FakeLanguagePluginContractTest extends LanguagePluginContract {

    @Override
    protected LanguagePlugin plugin() {
        return new FakePlugin("fake", ProjectType.MAVEN);
    }

    @Override
    protected SourceTree tree() {
        return new InMemorySourceTreeReader().file("/workspace/project", "pom.xml", "<project/>")
                .open(new com.quancrypt.analyzer.domain.model.AnalysisRoot("/workspace/project"));
    }

    @Test
    void theDoubleIsRegisteredLikeAnyPlugin() {
        assertThat(plugin().info().id()).isEqualTo("fake");
    }
}

