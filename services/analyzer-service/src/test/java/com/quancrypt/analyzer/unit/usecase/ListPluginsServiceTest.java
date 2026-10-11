package com.quancrypt.analyzer.unit.usecase;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.fake.FakePlugin;
import com.quancrypt.analyzer.port.inbound.PluginView;
import com.quancrypt.analyzer.usecase.ListPluginsService;
import com.quancrypt.analyzer.usecase.PluginSelector;
import java.util.List;
import org.junit.jupiter.api.Test;

class ListPluginsServiceTest {

    @Test
    void pluginsAreListedById() {
        ListPluginsService service = new ListPluginsService(new PluginSelector(List.of(
                new FakePlugin("zeta", ProjectType.MAVEN), new FakePlugin("java", ProjectType.GRADLE, ProjectType.MAVEN))));

        assertThat(service.list()).containsExactly(
                new PluginView("java", "Fake java", "1.0.0", List.of("GRADLE", "MAVEN")),
                new PluginView("zeta", "Fake zeta", "1.0.0", List.of("MAVEN")));
    }

    @Test
    void noPluginsIsAnEmptyList() {
        assertThat(new ListPluginsService(new PluginSelector(List.of())).list()).isEmpty();
    }
}
