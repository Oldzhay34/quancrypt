package com.quancrypt.core.infrastructure.persistence.plan;

import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.PageResult;
import com.quancrypt.core.domain.model.Plan;
import com.quancrypt.core.domain.model.PlanItem;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.PlanItemStates;
import com.quancrypt.core.domain.model.RiskFactor;
import com.quancrypt.core.domain.model.RiskScore;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.PlanReader;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads plans and their items; risk factors of a page of items come from one extra query (no N+1). Items are ordered by risk, highest first. */
public final class JdbcPlanReader implements PlanReader {

    private static final String ITEM_COLUMNS = "pi.id, pi.plan_id, pi.finding_id, pi.strategy, pi.effort, pi.risk_score, pi.state, pi.version";
    private static final String ITEM_ORDER = " ORDER BY pi.risk_score DESC, pi.id";

    private final JdbcClient jdbc;

    public JdbcPlanReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    /** An item row before its risk factors are attached. */
    private record ItemRow(UUID id, UUID planId, UUID findingId, StrategyCode strategy, Effort effort, RiskScore score,
                           PlanItemStateCode state, int version) {
        PlanItem with(List<RiskFactor> factors) {
            return new PlanItem(id, planId, findingId, strategy, effort, score, PlanItemStates.of(state), version, factors);
        }
    }

    @Override
    public Optional<Plan> byScan(UUID scanId) {
        return jdbc.sql("SELECT id, scan_id, created_at FROM plan WHERE scan_id = :scanId").param("scanId", scanId)
                .query((rs, n) -> new Plan(Sql.uuid(rs, "id"), Sql.uuid(rs, "scan_id"), Sql.instant(rs, "created_at"))).optional();
    }

    @Override
    public PageResult<PlanItem> items(UUID planId, Optional<PlanItemStateCode> state, int page, int size) {
        String filter = " WHERE pi.plan_id = :planId AND (CAST(:state AS varchar) IS NULL OR pi.state = :state)";
        String stateCode = state.map(Enum::name).orElse(null);
        List<ItemRow> rows = jdbc.sql("SELECT " + ITEM_COLUMNS + " FROM plan_item pi" + filter + ITEM_ORDER + " LIMIT :size OFFSET :offset")
                .param("planId", planId).param("state", stateCode).param("size", size).param("offset", Sql.offset(page, size))
                .query(JdbcPlanReader::item).list();
        long total = jdbc.sql("SELECT count(*) FROM plan_item pi" + filter).param("planId", planId).param("state", stateCode)
                .query(Long.class).single();
        return new PageResult<>(attachFactors(rows), page, size, total);
    }

    @Override
    public List<PlanItem> allItems(UUID planId) {
        return attachFactors(jdbc.sql("SELECT " + ITEM_COLUMNS + " FROM plan_item pi WHERE pi.plan_id = :planId" + ITEM_ORDER)
                .param("planId", planId).query(JdbcPlanReader::item).list());
    }

    @Override
    public Optional<PlanItem> item(UUID itemId) {
        return jdbc.sql("SELECT " + ITEM_COLUMNS + " FROM plan_item pi WHERE pi.id = :id").param("id", itemId)
                .query(JdbcPlanReader::item).optional()
                .map(row -> attachFactors(List.of(row)).getFirst());
    }

    @Override
    public Optional<UUID> projectIdOfItem(UUID itemId) {
        return jdbc.sql("""
                SELECT s.project_id FROM plan_item pi JOIN plan p ON p.id = pi.plan_id JOIN scan s ON s.id = p.scan_id
                WHERE pi.id = :id""")
                .param("id", itemId).query(UUID.class).optional();
    }

    private List<PlanItem> attachFactors(List<ItemRow> rows) {
        if (rows.isEmpty()) {
            return List.of();
        }
        Map<UUID, List<RiskFactor>> factors = new HashMap<>();
        jdbc.sql("""
                SELECT plan_item_id, rank_no, feature_name, shap_value FROM plan_item_risk_factor
                WHERE plan_item_id = ANY(CAST(:ids AS uuid[])) ORDER BY plan_item_id, rank_no""")
                .param("ids", Sql.textArray(rows.stream().map(ItemRow::id).toList()))
                .query(rs -> {
                    factors.computeIfAbsent(Sql.uuid(rs, "plan_item_id"), k -> new ArrayList<>())
                            .add(new RiskFactor(rs.getInt("rank_no"), rs.getString("feature_name"), rs.getBigDecimal("shap_value")));
                });
        return rows.stream().map(r -> r.with(factors.getOrDefault(r.id(), List.of()))).toList();
    }

    private static ItemRow item(ResultSet rs, int rowNum) throws SQLException {
        return new ItemRow(
                Sql.uuid(rs, "id"),
                Sql.uuid(rs, "plan_id"),
                Sql.uuid(rs, "finding_id"),
                Sql.code(rs, "strategy", StrategyCode.class),
                Sql.code(rs, "effort", Effort.class),
                new RiskScore(rs.getBigDecimal("risk_score")),
                Sql.code(rs, "state", PlanItemStateCode.class),
                rs.getInt("version"));
    }
}
