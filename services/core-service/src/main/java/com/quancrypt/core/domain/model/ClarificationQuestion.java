package com.quancrypt.core.domain.model;

import java.util.List;
import java.util.Optional;

/** The five clarification questions of the project profile and the options each accepts (reference document). */
public enum ClarificationQuestion {
    TLS_TERMINATION(AnswerKind.OPTION, "APPLICATION", "INGRESS", "SERVICE_MESH", "LOAD_BALANCER", "UNKNOWN"),
    JDK_UPGRADE_POSSIBLE(AnswerKind.OPTION, "YES", "NO", "UNKNOWN"),
    HYBRID_INCAPABLE_PARTNERS(AnswerKind.OPTION, "YES", "NO", "UNKNOWN"),
    COMPLIANCE_REQUIREMENT(AnswerKind.OPTION_WITH_TEXT, "YES", "NO", "UNKNOWN"),
    DEVICE_HARDWARE_OPENSSL(AnswerKind.TEXT);

    public static final int MAX_FREE_TEXT = 500;

    private final AnswerKind kind;
    private final List<String> options;

    ClarificationQuestion(AnswerKind kind, String... options) {
        this.kind = kind;
        this.options = List.of(options);
    }

    public AnswerKind kind() {
        return kind;
    }

    public List<String> options() {
        return options;
    }

    /** Checks that an answer has the shape this question requires; throws {@link IllegalArgumentException} otherwise. */
    public void validate(Optional<String> option, Optional<String> freeText) {
        freeText.ifPresent(text -> {
            if (text.isBlank() || text.length() > MAX_FREE_TEXT) {
                throw new IllegalArgumentException("free text must be 1.." + MAX_FREE_TEXT + " characters");
            }
        });
        switch (kind) {
            case OPTION -> {
                requireOption(option);
                if (freeText.isPresent()) {
                    throw new IllegalArgumentException(name() + " does not accept free text");
                }
            }
            case OPTION_WITH_TEXT -> requireOption(option);
            case TEXT -> {
                if (option.isPresent() || freeText.isEmpty()) {
                    throw new IllegalArgumentException(name() + " requires free text and no option");
                }
            }
        }
    }

    private void requireOption(Optional<String> option) {
        if (option.isEmpty() || !options.contains(option.get())) {
            throw new IllegalArgumentException(name() + " requires one of " + options);
        }
    }
}
