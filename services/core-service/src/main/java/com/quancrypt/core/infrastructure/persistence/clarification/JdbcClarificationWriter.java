package com.quancrypt.core.infrastructure.persistence.clarification;

import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.ClarificationWriter;
import java.sql.Types;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

/** Upserts clarification answers, one per project and question, as one batch. */
public final class JdbcClarificationWriter implements ClarificationWriter {

    private final NamedParameterJdbcOperations batch;

    public JdbcClarificationWriter(NamedParameterJdbcOperations batch) {
        this.batch = batch;
    }

    @Override
    public void upsertAll(UUID projectId, List<ClarificationAnswer> answers) {
        if (answers.isEmpty()) {
            return;
        }
        SqlParameterSource[] rows = answers.stream()
                .map(a -> new MapSqlParameterSource()
                        .addValue("projectId", projectId)
                        .addValue("question", a.question().name())
                        .addValue("option", a.option().orElse(null), Types.VARCHAR)
                        .addValue("freeText", a.freeText().orElse(null), Types.VARCHAR)
                        .addValue("at", Sql.ts(a.answeredAt())))
                .toArray(SqlParameterSource[]::new);
        batch.batchUpdate("""
                INSERT INTO clarification_answer (project_id, question_code, option_code, free_text, answered_at)
                VALUES (:projectId, :question, :option, :freeText, :at)
                ON CONFLICT (project_id, question_code) DO UPDATE
                SET option_code = EXCLUDED.option_code, free_text = EXCLUDED.free_text, answered_at = EXCLUDED.answered_at""", rows);
    }
}
