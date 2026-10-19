package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.GrantConsentCommand;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.StartScanCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import com.quancrypt.core.port.inbound.UseCaseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

/**
 * acid-3nf-database section 7, concurrency: two threads change the same plan item and one gets 409; concurrent scan
 * starts, first consents and topology PUTs are settled by the database, not by luck.
 */
class ConcurrencyTest extends IntegrationTest {

    /** Runs the calls at the same moment and returns each outcome: null for success, the problem code otherwise. */
    private static List<ProblemCode> race(List<Callable<?>> calls) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(calls.size());
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Future<ProblemCode>> futures = new ArrayList<>();
            for (Callable<?> call : calls) {
                futures.add(pool.submit(() -> {
                    start.await();
                    try {
                        call.call();
                        return null;
                    } catch (UseCaseException e) {
                        return e.problem();
                    }
                }));
            }
            start.countDown();
            List<ProblemCode> outcomes = new ArrayList<>();
            for (Future<ProblemCode> f : futures) {
                outcomes.add(f.get(60, TimeUnit.SECONDS));
            }
            return outcomes;
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void twoThreadsChangingOnePlanItemOneGets409() throws Exception {
        UUID itemId = plannedItem("/work/demo");

        List<ProblemCode> outcomes = race(List.of(
                () -> transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, Optional.empty(), "UI")),
                () -> transitionPlanItem.execute(new TransitionPlanItemCommand(itemId, "APPROVED", 1, Optional.empty(), "UI"))));

        assertThat(outcomes).containsExactlyInAnyOrder(null, ProblemCode.CONCURRENT_MODIFICATION);
        assertThat(jdbc.sql("SELECT version FROM plan_item WHERE id = :id").param("id", itemId).query(Integer.class).single()).isEqualTo(2);
        assertThat(rows("plan_item_state_transition")).isEqualTo(2);
    }

    @Test
    void twoScanStartsOnOneProjectOneGets409() throws Exception {
        UUID projectId = project("/work/demo");

        List<ProblemCode> outcomes = race(List.of(
                () -> startScan.execute(new StartScanCommand(projectId, Optional.empty(), "UI")),
                () -> startScan.execute(new StartScanCommand(projectId, Optional.empty(), "UI"))));

        assertThat(outcomes).containsExactlyInAnyOrder(null, ProblemCode.SCAN_ALREADY_RUNNING);
        assertThat(rows("scan")).isEqualTo(1);
    }

    @Test
    void twoFirstConsentsOneGets409() throws Exception {
        UUID projectId = project("/work/demo");
        Callable<?> grant = () -> grantConsent.execute(
                new GrantConsentCommand(projectId, "MODEL_TRAINING", 2, Optional.empty(), Optional.empty(), "UI"));

        List<ProblemCode> outcomes = race(List.of(grant, grant));

        assertThat(outcomes).contains((ProblemCode) null);
        assertThat(outcomes).allMatch(o -> o == null || o == ProblemCode.CONCURRENT_MODIFICATION);
        assertThat(rows("consent")).isEqualTo(1);
    }

    @Test
    void concurrentTopologyPutsAreSerializedAndBothSucceed() throws Exception {
        UUID projectId = projectWithConsent("/work/demo");
        UUID scanId = runningScan(projectId);
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a")).createdIds();
        Callable<?> put = () -> recordTopology.execute(new RecordTopologyCommand(scanId,
                List.of(new NodeInput("gateway", "GATEWAY"), new NodeInput("account", "SERVICE")),
                List.of(new LinkInput("gateway", "account", "HTTP", true, true,
                        List.of(new CallSiteInput("src/main/java/Client.java", 5, 6, "CODE")), ids)), "UI"));

        List<ProblemCode> outcomes = race(List.of(put, put, put));

        assertThat(outcomes).containsOnlyNulls();
        assertThat(rows("topology")).isEqualTo(1);
        assertThat(rows("service_link")).isEqualTo(1);
        assertThat(jdbc.sql("SELECT count(*) FROM outbox_event WHERE event_type = 'topology_recorded'").query(Integer.class).single())
                .isEqualTo(1);
    }
}
