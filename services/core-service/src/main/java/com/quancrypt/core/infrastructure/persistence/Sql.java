package com.quancrypt.core.infrastructure.persistence;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Collection;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.SqlParameterValue;

/** Conversions between JDBC values and domain values; every adapter binds and reads columns through these. */
public final class Sql {

    private Sql() {
    }

    /** timestamptz parameter. */
    public static OffsetDateTime ts(Instant instant) {
        return OffsetDateTime.ofInstant(instant, ZoneOffset.UTC);
    }

    /** Nullable timestamptz parameter. */
    public static OffsetDateTime ts(Optional<Instant> instant) {
        return instant.map(Sql::ts).orElse(null);
    }

    public static Instant instant(ResultSet rs, String column) throws SQLException {
        return rs.getObject(column, OffsetDateTime.class).toInstant();
    }

    public static Optional<Instant> optInstant(ResultSet rs, String column) throws SQLException {
        return Optional.ofNullable(rs.getObject(column, OffsetDateTime.class)).map(OffsetDateTime::toInstant);
    }

    public static UUID uuid(ResultSet rs, String column) throws SQLException {
        return rs.getObject(column, UUID.class);
    }

    public static Optional<UUID> optUuid(ResultSet rs, String column) throws SQLException {
        return Optional.ofNullable(rs.getObject(column, UUID.class));
    }

    public static Optional<Integer> optInt(ResultSet rs, String column) throws SQLException {
        int value = rs.getInt(column);
        return rs.wasNull() ? Optional.empty() : Optional.of(value);
    }

    public static Optional<String> optString(ResultSet rs, String column) throws SQLException {
        return Optional.ofNullable(rs.getString(column));
    }

    public static <E extends Enum<E>> E code(ResultSet rs, String column, Class<E> type) throws SQLException {
        return Enum.valueOf(type, rs.getString(column));
    }

    /**
     * One array parameter for {@code = ANY(CAST(:p AS text[]))} or {@code uuid[]}: a list of any length binds as a single
     * value, unlike {@code IN (:p)}, which expands to one bind parameter per element.
     */
    public static SqlParameterValue textArray(Collection<?> values) {
        return new SqlParameterValue(Types.ARRAY, values.stream().map(String::valueOf).toArray(String[]::new));
    }

    /** OFFSET of a zero-based page. */
    public static long offset(int page, int size) {
        return (long) page * size;
    }
}
