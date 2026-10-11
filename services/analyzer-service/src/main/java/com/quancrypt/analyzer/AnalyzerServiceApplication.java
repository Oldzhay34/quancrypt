package com.quancrypt.analyzer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Bootstrap only; the composition root and the REST layer come in later phases (D-176). */
@SpringBootApplication
public class AnalyzerServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AnalyzerServiceApplication.class, args);
    }
}
