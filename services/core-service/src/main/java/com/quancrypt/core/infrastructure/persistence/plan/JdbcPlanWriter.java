package com.quancrypt.core.infrastructure.persistence.plan;

import com.quancrypt.core.domain.exception.ConcurrentModificationException;
import com.quancrypt.core.domain.exception.PlanAlreadyExistsException;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemTransition;
import com.quancrypt.core.domain.model.RiskFactor;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.port.outbound.PlanWriter;
import java.util.ArrayList;
import java.util.List;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * Writes plans and plan items. uq_plan_scan allows one plan per scan; item changes are optimistic (version and the
 * expected current state in the WHERE clause), and every transition row is checked by the allowed_transition foreign key.
 */
public final class JdbcPlanWriter implements PlanWriter {

    static final String ONE_PLAN_PER_SCAN = "uq_plan_scan";

    private static final String INSERT_TRANSITION = """
            INSERT INTO plan_item_state_transition (id, plan_item_id, from_state, to_state, transitioned_at, caller_kind)
            VALUES (:id, :itemId, :from, :to, :at, :caller)""";

    private final JdbcClient jdbc;
    private final NamedParameterJdbcOperations batch;

    public JdbcPlanWriter(JdbcClient jdbc, NamedParameterJdbcOperations batch) {
        this.jdbc = jdbc;
        this.batch = batch;
    }

    @Override
    public void insert(Plan plan) {
        try {
            jdbc.sql("INSERT INTO plan (id, scan_id, created_at) VALUES (:id, :scanId, :createdAt)")
                    .param("id", plan.id()).param("scanId", plan.scanId()).param("createdAt", Sql.ts(plan.createdAt())).update();
        } catch (DataIntegrityViolationException e) {
            if (SqlErrors.isUniqueViolation(e, ONE_PLAN_PER_SCAN)) {
                throw new PlanAlreadyExistsException();
            }
            throw e;
        }
    }

    @Override
    public void insertItems(List<PlanItem> items, List<PlanItemTransition> transitions) {
        List<SqlParameterSource> itemRows = new ArrayList<>();
        List<SqlParameterSource> factorRows = new ArrayList<>();
        for (PlanItem item : items) {
            itemRows.add(new MapSqlParameterSource()
                    .addValue("id", item.id()).addValue("planId", item.planId()).addValue("findingId", item.findingId())
                    .addValue("strategy", item.strategy().name()).addValue("effort", item.effort().name())
                    .addValue("score", item.riskScore().value()).addValue("state", item.state().code().name())
                    .addValue("version", item.version()));
            for (RiskFactor factor : item.riskFactors()) {
                factorRows.add(new MapSqlParameterSource()
                        .addValue("itemId", item.id()).addValue("rank", factor.rank()).addValue("name", factor.featureName())
                        .addValue("shap", factor.shapValue()));
            }
        }
        run("""
                INSERT INTO plan_item (id, plan_id, finding_id, strategy, effort, risk_score, state, version)
                VALUES (:id, :planId, :findingId, :strategy, :effort, :score, :state, :version)""", itemRows);
        run("""
                INSERT INTO plan_item_risk_factor (plan_item_id, rank_no, feature_name, shap_value)
                VALUES (:itemId, :rank, :name, :shap)""", factorRows);
        run(INSERT_TRANSITION, transitions.stream().map(JdbcPlanWriter::transition).toList());
    }

    @Override
    public void update(PlanItem updated, int expectedVersion, PlanItemTransition transition) {
        int rows = jdbc.sql("""
                UPDATE plan_item SET state = :to, version = :newVersion
                WHERE id = :id AND version = :expectedVersion AND state = :from""")
                .param("to", transition.to().name())
                .param("newVersion", updated.version())
                .param("id", updated.id())
                .param("expectedVersion", expectedVersion)
                .param("from", transition.from().name())
                .update();
        if (rows == 0) {
            throw new ConcurrentModificationException("plan item");
        }
        batch.update(INSERT_TRANSITION, transition(transition));
    }

    private static SqlParameterSource transition(PlanItemTransition t) {
        return new MapSqlParameterSource()
                .addValue("id", t.id()).addValue("itemId", t.planItemId()).addValue("from", t.from().name())
                .addValue("to", t.to().name()).addValue("at", Sql.ts(t.transitionedAt())).addValue("caller", t.caller().name());
    }

    private void run(String sql, List<SqlParameterSource> rows) {
        if (!rows.isEmpty()) {
            batch.batchUpdate(sql, rows.toArray(SqlParameterSource[]::new));
        }
    }
}
