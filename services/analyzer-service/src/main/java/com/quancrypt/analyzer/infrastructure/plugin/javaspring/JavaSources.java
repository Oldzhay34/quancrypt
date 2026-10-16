package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.quancrypt.analyzer.domain.exception.PathNotAllowedException;
import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.port.outbound.SourceTree;
import java.nio.charset.StandardCharsets;
import java.util.Optional;

/** Parses Java files with JavaParser (language level 25, tokens stored because line ranges need them; no symbol solving, nothing is compiled, FR-12). */
public final class JavaSources {

    /** Texts that make a file worth a look for the topology detectors; checked on the source text while it is at hand. */
    private static final java.util.List<String> TOPOLOGY_MARKERS = java.util.List.of("RestTemplate", "RestClient", "WebClient", "FeignClient",
            "ManagedChannelBuilder", "NettyChannelBuilder", "OkHttpChannelBuilder", "org.eclipse.paho", "jdk.tls.namedGroups", "getBundle");

    private final JavaParser parser;

    public JavaSources() {
        ParserConfiguration configuration = new ParserConfiguration();
        configuration.setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_25);
        configuration.setAttributeComments(false);
        configuration.setStoreTokens(true);
        configuration.setLexicalPreservationEnabled(false);
        this.parser = new JavaParser(configuration);
    }

    /**
     * The parsed unit, or empty when the file vanished, is not reachable or cannot be parsed at all. A reading limit (file size,
     * total bytes) is not swallowed: it fails the analysis (D-181).
     */
    public Optional<JavaUnit> parse(SourceTree tree, ProjectFile file) {
        try {
            return parseSource(file, new String(tree.read(file.path()), StandardCharsets.UTF_8));
        } catch (SourceNotFoundException | PathNotAllowedException e) {
            return Optional.empty();
        }
    }

    /** The parsed unit of source text already read (same failures as {@link #parse}); empty when it cannot be parsed. */
    public Optional<JavaUnit> parseSource(ProjectFile file, String source) {
        try {
            ParseResult<CompilationUnit> result = parser.parse(source);
            return result.getResult().map(unit -> new JavaUnit(file.path(), file.location(), unit,
                    TOPOLOGY_MARKERS.stream().anyMatch(source::contains)));
        } catch (StackOverflowError e) {
            // an absurdly deep expression: the file is skipped and counted, the analysis goes on
            return Optional.empty();
        }
    }
}
