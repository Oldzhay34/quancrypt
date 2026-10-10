package com.quancrypt.core.infrastructure.persistence.lookup;

import com.quancrypt.core.domain.model.RiskClass;
import com.quancrypt.core.domain.policy.RiskClassPolicy;
import com.quancrypt.core.infrastructure.persistence.Sql;
import com.quancrypt.core.port.outbound.RiskThresholdReader;
import java.math.BigDecimal;
import java.util.EnumMap;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;

/** Reads the risk class thresholds from the risk_class_threshold lookup (D-128). */
public final class JdbcRiskThresholdReader implements RiskThresholdReader {

    private final JdbcClient jdbc;

    public JdbcRiskThresholdReader(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public RiskClassPolicy policy() {
        Map<RiskClass, BigDecimal> thresholds = new EnumMap<>(RiskClass.class);
        jdbc.sql("SELECT risk_class, min_score FROM risk_class_threshold")
                .query(rs -> {
                    thresholds.put(Sql.code(rs, "risk_class", RiskClass.class), rs.getBigDecimal("min_score"));
                });
        return new RiskClassPolicy(thresholds);
    }
}
