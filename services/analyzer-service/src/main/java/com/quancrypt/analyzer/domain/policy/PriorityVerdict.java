package com.quancrypt.analyzer.domain.policy;

import com.quancrypt.analyzer.domain.model.Priority;

/** What the crypto-domain priority table says about a usage. */
public sealed interface PriorityVerdict {

    /** The table gives this priority; core-service accepts only this one. */
    record Derived(Priority priority) implements PriorityVerdict {
    }

    /** The usage needs no migration (strong symmetric or hash, quantum resistant): core-service would reject it. */
    record NotApplicable() implements PriorityVerdict {
    }

    /** Algorithm or usage context is unknown: the detector's own priority is sent and core-service takes it. */
    record Undetermined() implements PriorityVerdict {
    }
}
