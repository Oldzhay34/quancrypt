package com.quancrypt.analyzer.api.controller;

import com.quancrypt.analyzer.facade.AnalyzerFacade;
import com.quancrypt.analyzer.facade.dto.PluginListDto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** ListPlugins: the installed language plugins. */
@RestController
@RequestMapping("/api/v1/plugins")
public class PluginController {

    private final AnalyzerFacade analyzer;

    public PluginController(AnalyzerFacade analyzer) {
        this.analyzer = analyzer;
    }

    @GetMapping
    PluginListDto list() {
        return analyzer.plugins();
    }
}
