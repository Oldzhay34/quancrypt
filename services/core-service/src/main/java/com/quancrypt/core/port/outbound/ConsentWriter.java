package com.quancrypt.core.port.outbound;

import com.quancrypt.core.domain.model.Consent;

/** Writes consents. */
public interface ConsentWriter {

    /** Throws DuplicateConsentException when the project already has a consent of the type. */
    void insert(Consent consent);

    /** Optimistic update; throws ConcurrentModificationException when the stored version differs. */
    void update(Consent updated, int expectedVersion);
}
