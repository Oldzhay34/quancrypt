package com.quancrypt.analyzer.fake;

import com.quancrypt.analyzer.domain.model.CryptoUsage;
import com.quancrypt.analyzer.domain.model.PluginInfo;
import com.quancrypt.analyzer.domain.model.ProjectDescriptor;
import com.quancrypt.analyzer.domain.model.ProjectType;
import com.quancrypt.analyzer.domain.model.RuntimeInfo;
import com.quancrypt.analyzer.domain.model.ServiceGraph;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/** Test double of a language plugin with canned answers; it records which of its methods were called. */
public final class FakePlugin implements LanguagePlugin {

    private final PluginInfo info;
    private final Set<ProjectType> supported;
    private List<CryptoUsage> usages = List.of();
    private ServiceGraph graph = ServiceGraph.EMPTY;
    private RuntimeInfo runtime = RuntimeInfo.UNKNOWN;
    private final List<String> calls = new ArrayList<>();

    public FakePlugin(String id, ProjectType... supported) {
        this.supported = Set.of(supported);
        this.info = new PluginInfo(id, "Fake " + id, "1.0.0", this.supported.isEmpty() ? Set.of(ProjectType.MAVEN) : this.supported);
    }

    public FakePlugin usages(List<CryptoUsage> value) {
        this.usages = List.copyOf(value);
        return this;
    }

    public FakePlugin graph(ServiceGraph value) {
        this.graph = value;
        return this;
    }

    public FakePlugin runtime(RuntimeInfo value) {
        this.runtime = value;
        return this;
    }

    public List<String> calls() {
        return List.copyOf(calls);
    }

    @Override
    public PluginInfo info() {
        return info;
    }

    @Override
    public boolean supports(ProjectDescriptor project) {
        calls.add("supports");
        return supported.contains(project.type());
    }

    @Override
    public List<CryptoUsage> analyzeCrypto(SourceTree tree) {
        calls.add("analyzeCrypto");
        return usages;
    }

    @Override
    public ServiceGraph buildTopology(SourceTree tree) {
        calls.add("buildTopology");
        return graph;
    }

    @Override
    public RuntimeInfo runtimeInfo(SourceTree tree) {
        calls.add("runtimeInfo");
        return runtime;
    }
}
