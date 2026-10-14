package com.quancrypt.analyzer.unit.facade;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.quancrypt.analyzer.facade.AnalyzerFacade;
import com.quancrypt.analyzer.facade.dto.AnalysisRequestInput;
import com.quancrypt.analyzer.facade.dto.TopologyRequestInput;
import com.quancrypt.analyzer.facade.error.ApiProblemException;
import com.quancrypt.analyzer.facade.error.ProblemKind;
import com.quancrypt.analyzer.port.inbound.AnalysisView;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoCommand;
import com.quancrypt.analyzer.port.inbound.AnalyzeCryptoUseCase;
import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import com.quancrypt.analyzer.port.inbound.BuildTopologyUseCase;
import com.quancrypt.analyzer.port.inbound.CbomView;
import com.quancrypt.analyzer.port.inbound.FindingView;
import com.quancrypt.analyzer.port.inbound.GetSnippetUseCase;
import com.quancrypt.analyzer.port.inbound.ListPluginsUseCase;
import com.quancrypt.analyzer.port.inbound.PluginView;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.port.inbound.RuntimeView;
import com.quancrypt.analyzer.port.inbound.SnippetLineView;
import com.quancrypt.analyzer.port.inbound.SnippetView;
import com.quancrypt.analyzer.port.inbound.StatsView;
import com.quancrypt.analyzer.port.inbound.TopologyView;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** The facade only builds commands, maps views to DTOs and failures to the problem types of the contract. */
class AnalyzerFacadeTest {

    private static final UUID ID = UUID.fromString("00000000-0000-4000-8000-0000000000aa");

    private final List<AnalyzeCryptoCommand> commands = new ArrayList<>();

    private AnalyzerFacade facade(AnalyzeCryptoUseCase analyze) {
        BuildTopologyUseCase topology = command -> new TopologyView(List.of(), List.of());
        GetSnippetUseCase snippet = query -> new SnippetView(query.path(), List.of(new SnippetLineView(query.line(), "text")));
        ListPluginsUseCase plugins = () -> List.of(new PluginView("java-spring", "Java", "1.0.0", List.of("MAVEN")));
        return new AnalyzerFacade(analyze, topology, snippet, plugins);
    }

    private AnalyzerFacade recording() {
        return facade(command -> {
            commands.add(command);
            FindingView finding = new FindingView("a/B.java", Optional.of(3), Optional.of(4), "RSA", "B#c", "RSA", Optional.empty(),
                    Optional.of("OAEP"), Optional.empty(), Optional.of(2048), "ENCRYPTION", "CODE", "P1", Optional.empty(), 0.9, "jca.cipher");
            return new AnalysisView(ID, "MAVEN", new RuntimeView(Optional.of("25"), Optional.empty()), List.of(finding),
                    new CbomView("1.6", "{\"bomFormat\":\"CycloneDX\",\"specVersion\":\"1.6\"}"), new StatsView(7, 1, 12));
        });
    }

    @Test
    void includeTestsDefaultsToTrueAndAbsentValuesBecomeNull() {
        var dto = recording().analyze(new AnalysisRequestInput("/workspace/p", null));

        assertThat(commands).singleElement().satisfies(c -> {
            assertThat(c.root()).isEqualTo("/workspace/p");
            assertThat(c.includeTests()).isTrue();
        });
        assertThat(dto.runtime().javaVersion()).isEqualTo("25");
        assertThat(dto.runtime().springBootVersion()).isNull();
        assertThat(dto.findings()).singleElement().satisfies(f -> {
            assertThat(f.lineStart()).isEqualTo(3);
            assertThat(f.mode()).isNull();
            assertThat(f.padding()).isEqualTo("OAEP");
            assertThat(f.keySizeBits()).isEqualTo(2048);
            assertThat(f.library()).isNull();
        });
        assertThat(dto.cbom()).contains("CycloneDX");
        assertThat(dto.stats().durationMs()).isEqualTo(12);
    }

    @Test
    void includeTestsFalseIsPassedOn() {
        recording().analyze(new AnalysisRequestInput("/workspace/p", false));

        assertThat(commands.get(0).includeTests()).isFalse();
    }

    @Test
    void aMissingOrBlankRootIsAValidationFailure() {
        AnalyzerFacade facade = recording();

        for (AnalysisRequestInput body : new AnalysisRequestInput[] {null, new AnalysisRequestInput(null, true), new AnalysisRequestInput(" ", true)}) {
            assertThatThrownBy(() -> facade.analyze(body)).isInstanceOfSatisfying(ApiProblemException.class,
                    e -> assertThat(e.kind()).isEqualTo(ProblemKind.VALIDATION_FAILED));
        }
        assertThatThrownBy(() -> facade.topology(new TopologyRequestInput(null))).isInstanceOf(ApiProblemException.class);
        assertThat(commands).isEmpty();
    }

    @Test
    void everyProblemCodeOfAUseCaseBecomesItsProblemKind() {
        for (ProblemCode code : ProblemCode.values()) {
            AnalyzerFacade facade = facade(command -> {
                throw new AnalyzerUseCaseException(code, "fixed sentence");
            });

            assertThatThrownBy(() -> facade.analyze(new AnalysisRequestInput("/workspace/p", true)))
                    .isInstanceOfSatisfying(ApiProblemException.class, e -> {
                        assertThat(e.kind().code()).isEqualTo(code.code());
                        assertThat(e.getMessage()).isEqualTo("fixed sentence");
                    });
        }
        assertThat(ProblemKind.ANALYSIS_TIMEOUT.status()).isEqualTo(504);
        assertThat(ProblemKind.UNSUPPORTED_PROJECT.status()).isEqualTo(422);
        assertThat(ProblemKind.PATH_NOT_ALLOWED.status()).isEqualTo(400);
        assertThat(ProblemKind.NOT_FOUND.status()).isEqualTo(404);
        assertThat(ProblemKind.ANALYSIS_TIMEOUT.type()).isEqualTo("https://quancrypt.local/problems/analysis-timeout");
    }

    @Test
    void anUnexpectedFailureIsNotMistakenForAContractProblem() {
        AnalyzerFacade facade = facade(command -> {
            throw new IllegalStateException("defect");
        });

        assertThatThrownBy(() -> facade.analyze(new AnalysisRequestInput("/workspace/p", true))).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void snippetsPluginsAndTopologyAreMapped() {
        AnalyzerFacade facade = recording();

        assertThat(facade.snippet("/workspace/p", "a.txt", 4, 3).lines()).singleElement().satisfies(l -> assertThat(l.number()).isEqualTo(4));
        assertThat(facade.plugins().plugins()).singleElement().satisfies(p -> assertThat(p.projectTypes()).containsExactly("MAVEN"));
        assertThat(facade.topology(new TopologyRequestInput("/workspace/p")).nodes()).isEmpty();
    }
}
