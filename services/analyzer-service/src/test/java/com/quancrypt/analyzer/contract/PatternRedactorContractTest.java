package com.quancrypt.analyzer.contract;

import com.quancrypt.analyzer.infrastructure.redaction.PatternRedactor;
import com.quancrypt.analyzer.infrastructure.redaction.RedactionRules;
import com.quancrypt.analyzer.port.outbound.Redactor;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** The real redactor keeps the contract of the port (D-179): the line count and the masking of private key blocks. */
class PatternRedactorContractTest extends RedactorContract {

    @Override
    protected Redactor redactor() {
        try (InputStream in = Files.newInputStream(Path.of(System.getProperty("quancrypt.contracts.dir"), "redaction-rules.yaml"))) {
            return new PatternRedactor(RedactionRules.parse(in));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
