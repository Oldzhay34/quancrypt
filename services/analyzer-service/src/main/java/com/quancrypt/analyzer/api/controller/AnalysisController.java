package com.quancrypt.analyzer.api.controller;

import com.quancrypt.analyzer.api.dto.AnalysisResponse;
import com.quancrypt.analyzer.facade.AnalyzerFacade;
import com.quancrypt.analyzer.facade.dto.AnalysisRequestInput;
import com.quancrypt.analyzer.api.dto.TopologyResponse;
import com.quancrypt.analyzer.facade.dto.TopologyRequestInput;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** AnalyzeCrypto and BuildTopology: synchronous, side-effect free, internal callers only (D-172, D-178a). */
@RestController
@RequestMapping("/api/v1")
public class AnalysisController {

    private final AnalyzerFacade analyzer;

    public AnalysisController(AnalyzerFacade analyzer) {
        this.analyzer = analyzer;
    }

    @PostMapping("/analyses")
    AnalysisResponse analyze(@RequestBody AnalysisRequestInput body) {
        return AnalysisResponse.of(analyzer.analyze(body));
    }

    @PostMapping("/topologies")
    TopologyResponse topology(@RequestBody TopologyRequestInput body) {
        return TopologyResponse.of(analyzer.topology(body));
    }
}
