package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.quancrypt.core.fake.Problems;
import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;

/**
 * acid-3nf-database section 7, invalid state transition: the domain refuses PLANNED to VERIFIED with 409, and the
 * database refuses the same transition row through the allowed_transition foreign key even when the domain is bypassed.
 */
class InvalidTransitionTest extends IntegrationTest {

    @Test
    void domainRejectsAnInvalidTransition() {
        UUID itemId = plannedItem("/work/demo");

        Problems.assertProblem(() -> transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "VERIFIED", 1, Optional.empty(), "UI")),
                ProblemCode.INVALID_STATE_TRANSITION);

        assertThat(jdbc.sql("SELECT state FROM plan_item WHERE id = :id").param("id", itemId).query(String.class).single()).isEqualTo("PLANNED");
        assertThat(rows("plan_item_state_transition")).isEqualTo(1);
    }

    @Test
    void databaseRejectsATransitionRowThatIsNotAllowed() {
        UUID itemId = plannedItem("/work/demo");

        Throwable failure = catchThrowable(() -> jdbc.sql("""
                INSERT INTO plan_item_state_transition (id, plan_item_id, from_state, to_state, transitioned_at, caller_kind)
                VALUES (gen_random_uuid(), :item, 'PLANNED', 'VERIFIED', now(), 'UI')""").param("item", itemId).update());

        assertThat(failure).isInstanceOf(DataIntegrityViolationException.class);
        assertThat(SqlErrors.constraint(failure)).contains("fk_plan_item_state_transition_from_state_to_state");
    }
}
