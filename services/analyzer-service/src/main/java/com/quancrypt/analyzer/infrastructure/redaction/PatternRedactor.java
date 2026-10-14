package com.quancrypt.analyzer.infrastructure.redaction;

import com.quancrypt.analyzer.port.outbound.Redactor;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Matcher;

/**
 * The {@link Redactor} of contracts/redaction-rules.yaml (D-179). The lines of a file are joined, the rules run over the
 * whole text in their order and the high-entropy rule last, so a match that spans lines (a private key block) is found.
 * A replaced span becomes one marker per line it touched, so the line count never changes and every touched line is
 * masked. Text longer than {@code max_input_length} is not scanned and every line becomes the too-long marker (fail
 * closed); the text is never cut into chunks, because a key block on a chunk border would escape.
 */
public final class PatternRedactor implements Redactor {

    private final RedactionRules rules;

    public PatternRedactor(RedactionRules rules) {
        this.rules = Objects.requireNonNull(rules, "rules");
    }

    @Override
    public List<String> redactLines(List<String> lines) {
        if (lines.isEmpty()) {
            return List.of();
        }
        String text = String.join("\n", lines);
        if (text.length() > rules.maxInputLength()) {
            return Collections.nCopies(lines.size(), rules.marker(RedactionRules.TOO_LONG_RULE));
        }
        String out = text;
        for (RedactionRules.PatternRule rule : rules.patterns()) {
            out = apply(rule, out);
        }
        out = highEntropy(out);
        List<String> result = new ArrayList<>(List.of(out.split("\n", -1)));
        if (result.size() != lines.size()) {
            throw new IllegalStateException("the redactor changed the number of lines");
        }
        return List.copyOf(result);
    }

    private String apply(RedactionRules.PatternRule rule, String text) {
        Matcher m = rule.pattern().matcher(text);
        String marker = rules.marker(rule.id());
        StringBuilder sb = new StringBuilder();
        int last = 0;
        while (m.find()) {
            int group = rule.valueGroup();
            int start = group == 0 || m.start(group) < 0 ? m.start() : m.start(group);
            int end = group == 0 || m.start(group) < 0 ? m.end() : m.end(group);
            sb.append(text, last, start).append(markers(marker, text, start, end));
            last = end;
        }
        return sb.append(text, last, text.length()).toString();
    }

    private String highEntropy(String text) {
        RedactionRules.HighEntropyRule rule = rules.highEntropy();
        Matcher m = rule.tokenPattern().matcher(text);
        String marker = rules.marker(rule.id());
        StringBuilder sb = new StringBuilder();
        int last = 0;
        while (m.find()) {
            String token = m.group();
            boolean secret = token.length() >= rule.minLength() && shannonBitsPerChar(token) >= rule.minBitsPerChar();
            if (secret) {
                sb.append(text, last, m.start()).append(markers(marker, text, m.start(), m.end()));
                last = m.end();
            }
        }
        return sb.append(text, last, text.length()).toString();
    }

    /** One marker for every line the span touches: as many markers as the span has line breaks, plus one. */
    private static String markers(String marker, String text, int start, int end) {
        int breaks = 0;
        for (int i = start; i < end; i++) {
            if (text.charAt(i) == '\n') {
                breaks++;
            }
        }
        return breaks == 0 ? marker : String.join("\n", Collections.nCopies(breaks + 1, marker));
    }

    /** Shannon entropy of the character distribution of the token, in bits per character. */
    static double shannonBitsPerChar(String token) {
        Map<Integer, Integer> counts = new HashMap<>();
        token.codePoints().forEach(c -> counts.merge(c, 1, Integer::sum));
        double length = token.codePointCount(0, token.length());
        double bits = 0;
        for (int count : counts.values()) {
            double p = count / length;
            bits -= p * (Math.log(p) / Math.log(2));
        }
        return bits;
    }
}
