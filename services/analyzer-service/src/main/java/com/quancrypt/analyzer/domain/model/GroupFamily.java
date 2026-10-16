package com.quancrypt.analyzer.domain.model;

/** Whether the key exchange groups a TLS endpoint offers are classical only or include a hybrid post-quantum group (D-208). */
public enum GroupFamily {
    CLASSICAL, HYBRID
}
