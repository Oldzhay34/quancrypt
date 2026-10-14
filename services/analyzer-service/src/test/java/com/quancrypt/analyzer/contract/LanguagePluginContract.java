package com.quancrypt.analyzer.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

/**
 * The contract every LanguagePlugin keeps (LSP): it describes itself consistently, supports exactly the project types it
 * names, gives the same answer for the same tree, leaves the tree unchanged and never answers null.
 */
public abstract class LanguagePluginContract {

    protected abstract LanguagePlugin plugin();

    /** A small project the plugin can analyze. */
    protected abstract SourceTree tree();

    @Test
    void itSupportsExactlyTheProjectTypesItDescribesItselfWith() {
        LanguagePlugin plugin = plugin();
        AnalysisRoot root = new AnalysisRoot("/workspace/project");

        for (ProjectType type : ProjectType.values()) {
            assertThat(plugin.supports(new ProjectDescriptor(root, type))).as(type.name()).isEqualTo(plugin.info().projectTypes().contains(type));
        }
        assertThat(plugin.info()).isEqualTo(plugin.info());
    }

    @Test
    void theSameTreeGivesTheSameAnswers() {
        LanguagePlugin plugin = plugin();
        SourceTree tree = tree();

        assertThat(plugin.analyzeCrypto(tree)).isEqualTo(plugin.analyzeCrypto(tree));
        assertThat(plugin.buildTopology(tree)).isEqualTo(plugin.buildTopology(tree));
        assertThat(plugin.runtimeInfo(tree)).isEqualTo(plugin.runtimeInfo(tree));
    }

    @Test
    void analyzingNeverChangesTheTree() {
        LanguagePlugin plugin = plugin();
        SourceTree tree = tree();
        var before = tree.files().stream().map(file -> file.value() + ":" + Arrays.hashCode(tree.read(file))).toList();

        plugin.analyzeCrypto(tree);
        plugin.buildTopology(tree);
        plugin.runtimeInfo(tree);

        assertThat(tree.files().stream().map(file -> file.value() + ":" + Arrays.hashCode(tree.read(file))).toList()).isEqualTo(before);
    }

    @Test
    void noAnswerIsNull() {
        LanguagePlugin plugin = plugin();
        SourceTree tree = tree();

        assertThat(plugin.analyzeCrypto(tree)).isNotNull();
        assertThat(plugin.buildTopology(tree)).isNotNull();
        assertThat(plugin.runtimeInfo(tree)).isNotNull();
        assertThat(plugin.info().id()).matches("[a-z0-9.-]{1,64}");
    }
}

