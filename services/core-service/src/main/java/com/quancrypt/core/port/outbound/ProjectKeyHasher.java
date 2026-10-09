package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.ProjectKey;

/** Computes project keys. */
public interface ProjectKeyHasher {

    /** HMAC-SHA256 of the identity with the anonymization salt; the identity itself is never stored. */
    ProjectKey hash(String identity);
}
