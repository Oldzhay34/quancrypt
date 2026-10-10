package com.quancrypt.core.infrastructure.anonymization;

import java.util.HashMap;
import java.util.Map;
import java.util.regex.Matcher;

/**
 * Applies the redaction rules in order, then the high-entropy rule; replaced spans become "[REDACTED:<rule>]". Text
 * longer than max_input_length is not scanned and comes back as "[REDACTED:max_input_length]" (fail closed).
 */
public final class Redactor {

    private final RedactionRules rules;

    public Redactor(RedactionRules rules) {
        this.rules = rules;
    }

    public String redact(String text) {
        if (text.length() > rules.maxInputLength()) {
            return rules.marker(RedactionRules.TOO_LONG_RULE);
        }
        String out = text;
        for (RedactionRules.PatternRule rule : rules.patterns()) {
            out = apply(rule, out);
        }
        return highEntropy(out);
    }

    private String apply(RedactionRules.PatternRule rule, String text) {
        Matcher m = rule.pattern().matcher(text);
        StringBuilder sb = new StringBuilder();
        String marker = rules.marker(rule.id());
        while (m.find()) {
            String replacement;
            if (rule.valueGroup() == 0 || m.start(rule.valueGroup()) < 0) {
                replacement = marker;
            } else {
                int group = rule.valueGroup();
                replacement = text.substring(m.start(), m.start(group)) + marker + text.substring(m.end(group), m.end());
            }
            m.appendReplacement(sb, Matcher.quoteReplacement(replacement));
        }
        m.appendTail(sb);
        return sb.toString();
    }

    private String highEntropy(String text) {
        RedactionRules.HighEntropyRule rule = rules.highEntropy();
        Matcher m = rule.tokenPattern().matcher(text);
        StringBuilder sb = new StringBuilder();
        String marker = rules.marker(rule.id());
        while (m.find()) {
            String token = m.group();
            boolean secret = token.length() >= rule.minLength() && shannonBitsPerChar(token) >= rule.minBitsPerChar();
            m.appendReplacement(sb, Matcher.quoteReplacement(secret ? marker : token));
        }
        m.appendTail(sb);
        return sb.toString();
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
