package com.quancrypt.core.domain.policy;

import com.quancrypt.core.domain.model.Priority;

/** What the priority table says about one crypto usage. */
public sealed interface PriorityVerdict {

    /** The table yields exactly this priority. */
    record Derived(Priority priority) implements PriorityVerdict {
    }

    /** The usage needs no migration (strong symmetric or hash algorithm, or already quantum resistant). */
    record NotApplicable() implements PriorityVerdict {
    }

    /** The table cannot decide (unknown algorithm or context); the caller's priority stands. */
    record Undetermined() implements PriorityVerdict {
    }
}
