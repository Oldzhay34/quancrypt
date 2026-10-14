package com.quancrypt.analyzer.infrastructure.config;

import com.quancrypt.analyzer.domain.model.CanonicalNames;
import com.quancrypt.analyzer.infrastructure.cbom.CycloneDxCbomWriter;
import com.quancrypt.analyzer.infrastructure.dictionary.CanonicalDictionaryLoader;
import com.quancrypt.analyzer.infrastructure.filesystem.DeadlineSourceTreeReader;
import com.quancrypt.analyzer.infrastructure.filesystem.FileSystemSourceTreeReader;
import com.quancrypt.analyzer.infrastructure.id.RandomIdGenerator;
import com.quancrypt.analyzer.infrastructure.plugin.javaspring.JavaSpringPlugins;
import com.quancrypt.analyzer.infrastructure.redaction.PatternRedactor;
import com.quancrypt.analyzer.infrastructure.redaction.RedactionRules;
import com.quancrypt.analyzer.infrastructure.time.SystemClock;
import com.quancrypt.analyzer.port.outbound.CbomWriter;
import com.quancrypt.analyzer.port.outbound.Clock;
import com.quancrypt.analyzer.port.outbound.IdGenerator;
import com.quancrypt.analyzer.port.outbound.LanguagePlugin;
import com.quancrypt.analyzer.port.outbound.Redactor;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.time.Duration;
import java.util.List;
import java.util.function.UnaryOperator;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

/** The driven adapters of the outbound ports (composition root, part 1). */
@Configuration(proxyBeanMethods = false)
public class AdapterConfig {

    @Bean
    Clock clock() {
        return new SystemClock(java.time.Clock.systemUTC());
    }

    @Bean
    IdGenerator idGenerator() {
        return new RandomIdGenerator();
    }

    @Bean
    CanonicalNames canonicalNames() {
        return new CanonicalNames(new CanonicalDictionaryLoader().loadFromClasspath());
    }

    /** Every opened tree gets the analysis time budget (D-199); the file system reader below it enforces the reading limits. */
    @Bean
    @Primary
    SourceTreeReader sourceTreeReader(Clock clock, @Value("${analyzer.time-budget-seconds}") long budgetSeconds) {
        return new DeadlineSourceTreeReader(new FileSystemSourceTreeReader(), clock, Duration.ofSeconds(budgetSeconds));
    }

    /** Reading one file for a snippet has no time budget: the contract declares the 504 for analyses only (D-199). */
    @Bean
    SourceTreeReader plainSourceTreeReader() {
        return new FileSystemSourceTreeReader();
    }

    @Bean
    Redactor redactor() {
        return new PatternRedactor(RedactionRules.fromClasspath());
    }

    @Bean
    CbomWriter cbomWriter(Clock clock, IdGenerator ids, ObjectProvider<BuildProperties> build) {
        BuildProperties properties = build.getIfAvailable();
        String version = properties == null ? null : properties.getVersion();
        return new CycloneDxCbomWriter(clock, ids, version == null ? "dev" : version);
    }

    /** The plugin's findings pass the shared redaction rules, so a secret in a literal never becomes a name (guardrails section 5). */
    @Bean
    List<LanguagePlugin> languagePlugins(CanonicalNames names, Redactor redactor) {
        UnaryOperator<String> sanitizer = text -> redactor.redactLines(List.of(text)).get(0).equals(text) ? text : "unrecognized";
        return List.of(JavaSpringPlugins.standard(names, sanitizer));
    }
}
