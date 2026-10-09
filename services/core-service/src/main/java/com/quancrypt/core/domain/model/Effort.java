package com.quancrypt.core.domain.model;

/** Effort grade of a plan item (D-124). */
public enum Effort {
    S,
    M,
    L;

    /** One grade higher; {@link #L} stays {@link #L}. */
    public Effort raised() {
        return switch (this) {
            case S -> M;
            case M, L -> L;
        };
    }
}
