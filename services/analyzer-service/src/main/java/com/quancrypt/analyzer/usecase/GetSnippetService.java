package com.quancrypt.analyzer.usecase;

import com.quancrypt.analyzer.domain.exception.SourceNotFoundException;
import com.quancrypt.analyzer.domain.model.AllowedRoots;
import com.quancrypt.analyzer.domain.model.AnalysisRoot;
import com.quancrypt.analyzer.domain.model.RelativePath;
import com.quancrypt.analyzer.domain.model.Snippet;
import com.quancrypt.analyzer.domain.model.SnippetLine;
import com.quancrypt.analyzer.domain.policy.SensitiveFilePolicy;
import com.quancrypt.analyzer.port.inbound.AnalyzerUseCaseException;
import com.quancrypt.analyzer.port.inbound.GetSnippetQuery;
import com.quancrypt.analyzer.port.inbound.GetSnippetUseCase;
import com.quancrypt.analyzer.port.inbound.ProblemCode;
import com.quancrypt.analyzer.port.inbound.SnippetView;
import com.quancrypt.analyzer.port.outbound.Redactor;
import com.quancrypt.analyzer.port.outbound.SourceTreeReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Reads a line and up to 10 lines on each side. The whole file goes through the redactor first, so a secret spanning
 * lines is masked even when the window starts inside it (guardrails-security, section 5; D-179); lines are cut to 4096
 * characters. Environment, keystore and private key files are refused (D-180).
 */
public final class GetSnippetService implements GetSnippetUseCase {

    public static final int MAX_LINE_LENGTH = 4096;

    private final AllowedRoots allowedRoots;
    private final SourceTreeReader reader;
    private final Redactor redactor;
    private final SensitiveFilePolicy sensitiveFiles;

    public GetSnippetService(AllowedRoots allowedRoots, SourceTreeReader reader, Redactor redactor, SensitiveFilePolicy sensitiveFiles) {
        this.allowedRoots = Objects.requireNonNull(allowedRoots, "allowedRoots");
        this.reader = Objects.requireNonNull(reader, "reader");
        this.redactor = Objects.requireNonNull(redactor, "redactor");
        this.sensitiveFiles = Objects.requireNonNull(sensitiveFiles, "sensitiveFiles");
    }

    @Override
    public SnippetView get(GetSnippetQuery query) {
        AnalysisRoot root = Inputs.root(allowedRoots, query.root());
        RelativePath path = Inputs.path(query.path());
        int line = Inputs.line(query.line());
        int context = Inputs.context(query.context());
        if (sensitiveFiles.isRefused(path) || java.util.Arrays.asList(query.root().toLowerCase(java.util.Locale.ROOT).split("/")).contains(".quancrypt")) {
            throw new AnalyzerUseCaseException(ProblemCode.PATH_NOT_ALLOWED, "snippets of secret-bearing files are not served");
        }
        return Failures.translate(() -> {
            List<String> raw = reader.open(root).readLines(path);
            List<String> lines = redactor.redactLines(raw);
            if (lines.size() != raw.size()) {
                throw new IllegalStateException("the redactor changed the number of lines");
            }
            if (line > lines.size()) {
                throw new SourceNotFoundException("the line is outside the file");
            }
            int first = Math.max(1, line - context);
            int last = Math.min(lines.size(), line + context);
            List<SnippetLine> window = new ArrayList<>();
            for (int number = first; number <= last; number++) {
                window.add(new SnippetLine(number, cut(lines.get(number - 1))));
            }
            return Views.snippet(new Snippet(path, window));
        });
    }

    private static String cut(String text) {
        if (text.length() <= MAX_LINE_LENGTH) {
            return text;
        }
        int end = Character.isHighSurrogate(text.charAt(MAX_LINE_LENGTH - 1)) ? MAX_LINE_LENGTH - 1 : MAX_LINE_LENGTH;
        return text.substring(0, end);
    }
}
