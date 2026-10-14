package com.quancrypt.analyzer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Bootstrap only; the composition root is infrastructure/config, the REST layer is api and facade (P3.3). */
@SpringBootApplication
public class AnalyzerServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AnalyzerServiceApplication.class, args);
    }
}
