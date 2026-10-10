package com.quancrypt.core.infrastructure.persistence.clarification;

import com.quancrypt.core.domain.model.ClarificationAnswer;
import com.quancrypt.core.domain.model.ClarificationQuestion;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.ClarificationReader;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads a project's clarification answers in the questions' order. */
public final class JdbcClarificationReader implements ClarificationReader {

    private final JdbcClient jdbc;

    public JdbcClarificationReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public List<ClarificationAnswer> list(UUID projectId) {
        return jdbc.sql("""
                SELECT a.question_code, a.option_code, a.free_text, a.answered_at
                FROM clarification_answer a JOIN clarification_question q ON q.code = a.question_code
                WHERE a.project_id = :projectId ORDER BY q.sort_order""")
                .param("projectId", projectId)
                .query((rs, n) -> new ClarificationAnswer(Sql.code(rs, "question_code", ClarificationQuestion.class),
                        Sql.optString(rs, "option_code"), Sql.optString(rs, "free_text"), Sql.instant(rs, "answered_at")))
                .list();
    }
}
