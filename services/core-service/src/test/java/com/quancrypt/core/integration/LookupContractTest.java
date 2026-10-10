package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.domain.model.AlgorithmFamily;
import com.quancrypt.core.domain.model.AnswerKind;
import com.quancrypt.core.domain.model.AuditAction;
import com.quancrypt.core.domain.model.CallerKind;
import com.quancrypt.core.domain.model.ClarificationQuestion;
import com.quancrypt.core.domain.model.ClassifiedBy;
import com.quancrypt.core.domain.model.ConsentType;
import com.quancrypt.core.domain.model.Effort;
import com.quancrypt.core.domain.model.EventType;
import com.quancrypt.core.domain.model.LocationKind;
import com.quancrypt.core.domain.model.NodeKind;
import com.quancrypt.core.domain.model.PlanItemStateCode;
import com.quancrypt.core.domain.model.PlanItemStates;
import com.quancrypt.core.domain.model.Priority;
import com.quancrypt.core.domain.model.Protocol;
import com.quancrypt.core.domain.model.QuantumStatus;
import com.quancrypt.core.domain.model.RiskClass;
import com.quancrypt.core.domain.model.ScanStatus;
import com.quancrypt.core.domain.model.StrategyCode;
import com.quancrypt.core.domain.model.UsageContext;
import com.quancrypt.core.integration.support.PostgresTestDatabase;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;

/**
 * The Java code lists match the lookup tables of the migration (D-153): every enum constant has a lookup row and the
 * other way round, strategy base efforts and quantum statuses agree, the allowed transitions are the State pattern's,
 * and the clarification questions and options are the same.
 */
class LookupContractTest {

    private final JdbcClient jdbc = JdbcClient.create(PostgresTestDatabase.get().app());

    private Set<String> codes(String table) {
        return new HashSet<>(jdbc.sql("SELECT code FROM " + table).query(String.class).list());
    }

    private static Set<String> names(Class<? extends Enum<?>> type) {
        return Arrays.stream(type.getEnumConstants()).map(Enum::name).collect(Collectors.toSet());
    }

    @Test
    void everyEnumHasExactlyTheLookupCodes() {
        Map<String, Class<? extends Enum<?>>> lookups = Map.ofEntries(
                Map.entry("quantum_status", QuantumStatus.class), Map.entry("algorithm_family", AlgorithmFamily.class),
                Map.entry("usage_context", UsageContext.class), Map.entry("location_kind", LocationKind.class),
                Map.entry("priority", Priority.class), Map.entry("effort_level", Effort.class), Map.entry("strategy", StrategyCode.class),
                Map.entry("risk_class", RiskClass.class), Map.entry("plan_item_state", PlanItemStateCode.class),
                Map.entry("scan_status", ScanStatus.class), Map.entry("node_kind", NodeKind.class), Map.entry("protocol", Protocol.class),
                Map.entry("consent_type", ConsentType.class), Map.entry("classified_by", ClassifiedBy.class),
                Map.entry("caller_kind", CallerKind.class), Map.entry("answer_kind", AnswerKind.class),
                Map.entry("audit_action", AuditAction.class), Map.entry("clarification_question", ClarificationQuestion.class));
        lookups.forEach((table, type) -> assertThat(codes(table)).as(table).isEqualTo(names(type)));
        assertThat(codes("event_type")).isEqualTo(Arrays.stream(EventType.values()).map(EventType::code).collect(Collectors.toSet()));
    }

    @Test
    void strategyBaseEffortsAndQuantumStatusesAgree() {
        Map<String, String> efforts = new HashMap<>();
        jdbc.sql("SELECT code, base_effort FROM strategy").query(rs -> {
            efforts.put(rs.getString(1), rs.getString(2));
        });
        for (StrategyCode strategy : StrategyCode.values()) {
            assertThat(efforts.get(strategy.name())).as(strategy.name()).isEqualTo(strategy.baseEffort().name());
        }
        Map<String, String> statuses = new HashMap<>();
        jdbc.sql("SELECT code, quantum_status FROM algorithm_family").query(rs -> {
            statuses.put(rs.getString(1), rs.getString(2));
        });
        for (AlgorithmFamily family : AlgorithmFamily.values()) {
            assertThat(statuses.get(family.name())).as(family.name()).isEqualTo(family.quantumStatus().map(Enum::name).orElse(null));
        }
    }

    @Test
    void allowedTransitionsAreTheStatePatternTransitions() {
        Set<String> inDatabase = new HashSet<>(jdbc.sql("SELECT from_state || '>' || to_state FROM allowed_transition").query(String.class).list());
        Set<String> inDomain = new HashSet<>();
        for (PlanItemStateCode from : PlanItemStateCode.values()) {
            PlanItemStates.of(from).allowedTargets().forEach(to -> inDomain.add(from + ">" + to));
        }
        assertThat(inDatabase).isEqualTo(inDomain);
    }

    @Test
    void clarificationQuestionsKindsAndOptionsAgree() {
        for (ClarificationQuestion question : ClarificationQuestion.values()) {
            String kind = jdbc.sql("SELECT answer_kind FROM clarification_question WHERE code = :code").param("code", question.name())
                    .query(String.class).single();
            List<String> options = jdbc.sql("SELECT option_code FROM clarification_option WHERE question_code = :code ORDER BY sort_order")
                    .param("code", question.name()).query(String.class).list();
            assertThat(kind).as(question.name()).isEqualTo(question.kind().name());
            assertThat(options).as(question.name()).isEqualTo(question.options());
        }
    }
}
