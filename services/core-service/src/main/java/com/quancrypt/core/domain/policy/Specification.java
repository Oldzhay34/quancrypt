package com.quancrypt.core.domain.policy;

import java.util.function.Predicate;

/** A named, combinable rule over a value (Specification pattern). */
@FunctionalInterface
public interface Specification<T> {

    boolean isSatisfiedBy(T candidate);

    default Specification<T> and(Specification<T> other) {
        return candidate -> isSatisfiedBy(candidate) && other.isSatisfiedBy(candidate);
    }

    default Specification<T> or(Specification<T> other) {
        return candidate -> isSatisfiedBy(candidate) || other.isSatisfiedBy(candidate);
    }

    default Specification<T> not() {
        return candidate -> !isSatisfiedBy(candidate);
    }

    static <T> Specification<T> of(Predicate<T> predicate) {
        return predicate::test;
    }
}
