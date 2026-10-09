package com.quancrypt.core.domain.policy;

import com.quancrypt.core.domain.exception.FindingRejectedException;
import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.CryptoUsage;
import com.quancrypt.core.domain.model.Priority;

/**
 * Checks the priority an analyzer sent against the table (D-149): the table is the single source of truth.
 * P0 is also accepted for AES and RSA, because ECB mode and PKCS#1 v1.5 padding cannot be derived from the fields.
 */
public final class PriorityPolicy {

    private final PriorityClassifier classifier;

    public PriorityPolicy(PriorityClassifier classifier) {
        this.classifier = classifier;
    }

    /** Returns the priority to store, or throws {@link FindingRejectedException}. */
    public Priority accept(CryptoUsage usage, Priority supplied) {
        if (supplied == Priority.P0 && (usage.algorithm() == AlgorithmFamily.AES || usage.algorithm() == AlgorithmFamily.RSA)) {
            return Priority.P0;
        }
        return switch (classifier.classify(usage)) {
            case PriorityVerdict.Derived derived -> {
                if (derived.priority() != supplied) {
                    throw new FindingRejectedException(FindingRejectedException.Reason.PRIORITY_MISMATCH,
                            "expected priority " + derived.priority() + " but got " + supplied);
                }
                yield supplied;
            }
            case PriorityVerdict.NotApplicable notApplicable -> throw new FindingRejectedException(
                    FindingRejectedException.Reason.NO_MIGRATION_NEEDED, "the finding needs no migration");
            case PriorityVerdict.Undetermined undetermined -> supplied;
        };
    }
}
