package com.quancrypt.analyzer.infrastructure.plugin.javaspring;

/** What the plugin does with an observation. */
public enum Role {
    /** Reported as a finding. */
    FINDING,
    /** Reported only when the file has no FINDING of the same algorithm family (a key was generated and used nowhere else). */
    FALLBACK,
    /** Never reported; supplies hints (a key size) to the findings of the same file and family. */
    SUPPORT
}
