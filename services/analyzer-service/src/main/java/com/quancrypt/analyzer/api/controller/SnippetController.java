package com.quancrypt.analyzer.api.controller;

import com.quancrypt.analyzer.facade.AnalyzerFacade;
import com.quancrypt.analyzer.facade.dto.SnippetDto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** GetSnippet: redacted lines around a finding. The root and the path are query parameters and are never logged. */
@RestController
@RequestMapping("/api/v1/snippets")
public class SnippetController {

    private final AnalyzerFacade analyzer;

    public SnippetController(AnalyzerFacade analyzer) {
        this.analyzer = analyzer;
    }

    @GetMapping
    SnippetDto get(@RequestParam String root, @RequestParam String path, @RequestParam int line,
            @RequestParam(defaultValue = "3") int context) {
        return analyzer.snippet(root, path, line, context);
    }
}
