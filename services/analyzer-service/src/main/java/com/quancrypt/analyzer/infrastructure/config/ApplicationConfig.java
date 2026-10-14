package com.quancrypt.analyzer.infrastructure.config;

import com.quancrypt.analyzer.api.BodyLimitFilter;
import com.quancrypt.analyzer.api.TraceIdFilter;
import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.policy.ProjectTypeDetector;
import com.quancrypt.analyzer.domain.policy.SensitiveFilePolicy;
import com.quancrypt.analyzer.facade.AnalyzerFacade;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoUseCase;
import com.quancrypt.analyzer.port.inbound.BuildTopologyUseCase;
import com.quancrypt.analyzer.port.inbound.GetSnippetUseCase;
import com.quancrypt.analyzer.port.inbound.ListPluginsUseCase;
import com.quancrypt.analyzer.port.outbound.CbomWriter;
import com.quancrypt.analyzer.port.outbound.Clock;
import com.quancrypt.analyzer.port.outbound.IdGenerator;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import com.quancrypt.analyzer.port.outbound.Redactor;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import com.quancrypt.analyzer.usecase.AnalyzeCryptoService;
import com.quancrypt.analyzer.usecase.BuildTopologyService;
import com.quancrypt.analyzer.usecase.GetSnippetService;
import com.quancrypt.analyzer.usecase.ListPluginsService;
import com.quancrypt.analyzer.usecase.PluginSelector;
import com.quancrypt.analyzer.usecase.ProjectOpener;
import java.util.Arrays;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/**
 * The use cases, the facade and the trace id filter (composition root, part 2). The use cases are plain objects, so this
 * is the only place that knows both them and Spring (hexagonal-service, section 3).
 */
@Configuration(proxyBeanMethods = false)
public class ApplicationConfig {

    @Bean
    AllowedRoots allowedRoots(@Value("${analyzer.allowed-roots}") String roots) {
        List<String> directories = Arrays.stream(roots.split(",")).map(String::strip).filter(s -> !s.isEmpty()).toList();
        return new AllowedRoots(directories);
    }

    @Bean
    ProjectOpener projectOpener(AllowedRoots allowedRoots, SourceTreeReader reader) {
        return new ProjectOpener(allowedRoots, reader, new ProjectTypeDetector());
    }

    @Bean
    PluginSelector pluginSelector(List<LanguagePlugin> plugins) {
        return new PluginSelector(plugins);
    }

    @Bean
    AnalyzeCryptoUseCase analyzeCrypto(ProjectOpener opener, PluginSelector plugins, CbomWriter cbomWriter, IdGenerator ids, Clock clock) {
        return new AnalyzeCryptoService(opener, plugins, cbomWriter, ids, clock);
    }

    @Bean
    BuildTopologyUseCase buildTopology(ProjectOpener opener, PluginSelector plugins) {
        return new BuildTopologyService(opener, plugins);
    }

    @Bean
    GetSnippetUseCase getSnippet(AllowedRoots allowedRoots, @Qualifier("plainSourceTreeReader") SourceTreeReader reader, Redactor redactor) {
        return new GetSnippetService(allowedRoots, reader, redactor, new SensitiveFilePolicy());
    }

    @Bean
    ListPluginsUseCase listPlugins(PluginSelector plugins) {
        return new ListPluginsService(plugins);
    }

    @Bean
    AnalyzerFacade analyzerFacade(AnalyzeCryptoUseCase analyze, BuildTopologyUseCase topology, GetSnippetUseCase snippet,
            ListPluginsUseCase plugins) {
        return new AnalyzerFacade(analyze, topology, snippet, plugins);
    }

    /** Right behind the trace id filter: a body above the limit is refused before anything reads it (D-205). */
    @Bean
    FilterRegistrationBean<BodyLimitFilter> bodyLimitFilter() {
        FilterRegistrationBean<BodyLimitFilter> registration = new FilterRegistrationBean<>(new BodyLimitFilter());
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 1);
        return registration;
    }

    /** Runs before everything else, so that even a 401 answer carries X-Trace-Id. */
    @Bean
    FilterRegistrationBean<TraceIdFilter> traceIdFilter() {
        FilterRegistrationBean<TraceIdFilter> registration = new FilterRegistrationBean<>(new TraceIdFilter());
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }
}
