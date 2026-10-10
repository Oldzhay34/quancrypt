package com.quancrypt.core.infrastructure.persistence;

import java.sql.SQLException;
import java.util.Optional;
import org.postgresql.util.PSQLException;
import org.postgresql.util.ServerErrorMessage;

/** Reads SQLSTATE and the violated constraint name from a failure; the name comes from the server, not the message text. */
public final class SqlErrors {

    public static final String UNIQUE_VIOLATION = "23505";
    public static final String SERIALIZATION_FAILURE = "40001";
    public static final String DEADLOCK_DETECTED = "40P01";

    private SqlErrors() {
    }

    public static Optional<String> sqlState(Throwable failure) {
        for (Throwable t = failure; t != null; t = t.getCause()) {
            if (t instanceof SQLException sql && sql.getSQLState() != null) {
                return Optional.of(sql.getSQLState());
            }
        }
        return Optional.empty();
    }

    public static Optional<String> constraint(Throwable failure) {
        for (Throwable t = failure; t != null; t = t.getCause()) {
            if (t instanceof PSQLException psql) {
                ServerErrorMessage message = psql.getServerErrorMessage();
                return message == null ? Optional.empty() : Optional.ofNullable(message.getConstraint());
            }
        }
        return Optional.empty();
    }

    /** True when the failure is a unique violation of the named constraint or index. */
    public static boolean isUniqueViolation(Throwable failure, String constraintName) {
        return sqlState(failure).filter(UNIQUE_VIOLATION::equals).isPresent()
                && constraint(failure).filter(constraintName::equals).isPresent();
    }
}
