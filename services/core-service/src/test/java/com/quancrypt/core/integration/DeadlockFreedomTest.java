package com.quancrypt.core.integration;

import static org.assertj.core.api.Assertions.assertThat;

import com.quancrypt.core.infrastructure.persistence.SqlErrors;
import com.quancrypt.core.integration.support.IntegrationTest;
import com.quancrypt.core.port.inbound.CallSiteInput;
import com.quancrypt.core.port.inbound.CompleteScanCommand;
import com.quancrypt.core.port.inbound.CreatePlanCommand;
import com.quancrypt.core.port.inbound.DeleteProjectCommand;
import com.quancrypt.core.port.inbound.LinkInput;
import com.quancrypt.core.port.inbound.NodeInput;
import com.quancrypt.core.port.inbound.ProblemCode;
import com.quancrypt.core.port.inbound.RecordFindingsCommand;
import com.quancrypt.core.port.inbound.RecordRuntimeProfileCommand;
import com.quancrypt.core.port.inbound.RecordTopologyCommand;
import com.quancrypt.core.port.inbound.RevokeConsentCommand;
import com.quancrypt.core.port.inbound.TransitionPlanItemCommand;
import com.quancrypt.core.port.inbound.UseCaseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

/**
 * D-143: every event-writing use case runs against DeleteProject in both start orders. The binding lock order
 * (project first) means no deadlock happens (the transaction runner reports no 40P01 retry), each call either succeeds
 * or gets 404, and after the deletion the outbox holds no pending event of the project except consent_revoked
 * (D-139a, D-147).
 */
class DeadlockFreedomTest extends IntegrationTest {

    private static final int ROUNDS = 3;

    /** Prepares a project for one race and returns the use case call to race against its deletion. */
    private record Contender(String name, Function<Integer, Runnable> prepare) {
    }

    private record Setup(UUID projectId, UUID scanId, List<UUID> findingIds) {
    }

    private Setup runningWithFinding(String identity) {
        UUID projectId = projectWithConsent(identity);
        UUID scanId = runningScan(projectId);
        List<UUID> ids = record(scanId, tlsFinding("src/main/java/Tls.java", "Tls#a")).createdIds();
        return new Setup(projectId, scanId, ids);
    }

    private List<Contender> contenders() {
        return List.of(
                new Contender("RecordRuntimeProfile", i -> {
                    UUID p = projectWithConsent("/work/profile-" + i);
                    return () -> recordRuntimeProfile.execute(new RecordRuntimeProfileCommand(p, "21", Optional.empty(), Optional.empty(), "UI"));
                }),
                new Contender("RecordFindings", i -> {
                    Setup s = runningWithFinding("/work/findings-" + i);
                    return () -> recordFindings.execute(new RecordFindingsCommand(s.scanId(),
                            List.of(tlsFinding("src/main/java/Other.java", "Other#b")), Optional.empty(), "UI"));
                }),
                new Contender("RecordTopology", i -> {
                    Setup s = runningWithFinding("/work/topology-" + i);
                    return () -> recordTopology.execute(new RecordTopologyCommand(s.scanId(),
                            List.of(new NodeInput("gateway", "GATEWAY"), new NodeInput("account", "SERVICE")),
                            List.of(new LinkInput("gateway", "account", "HTTP", true, true,
                                    List.of(new CallSiteInput("src/main/java/Client.java", 5, 6, "CODE")), s.findingIds())), "UI"));
                }),
                new Contender("CompleteScan", i -> {
                    Setup s = runningWithFinding("/work/complete-" + i);
                    return () -> completeScan.execute(new CompleteScanCommand(s.scanId(), "COMPLETED", Optional.empty(), "UI"));
                }),
                new Contender("CreatePlan", i -> {
                    Setup s = runningWithFinding("/work/plan-" + i);
                    complete(s.scanId());
                    return () -> createPlan.execute(new CreatePlanCommand(s.scanId(), assessAll(s.findingIds()), Optional.empty(), "UI"));
                }),
                new Contender("TransitionPlanItem", i -> {
                    UUID item = plannedItem("/work/transition-" + i);
                    return () -> transitionPlanItem.execute(new TransitionPlanItemCommand(item, "APPROVED", 1, Optional.empty(), "UI"));
                }),
                new Contender("RevokeConsent", i -> {
                    UUID p = projectWithConsent("/work/revoke-" + i);
                    return () -> revokeConsent.execute(new RevokeConsentCommand(p, "WAREHOUSE_ANALYTICS", 0, "UI"));
                }));
    }

    @Test
    void noEventWriterDeadlocksWithDeleteProjectInEitherOrder() throws Exception {
        int round = 0;
        for (Contender contender : contenders()) {
            for (int r = 0; r < ROUNDS; r++) {
                for (boolean deleteFirst : new boolean[] {false, true}) {
                    round++;
                    Runnable call = contender.prepare().apply(round);
                    UUID projectId = latestProject();
                    String projectKey = jdbc.sql("SELECT project_key FROM project WHERE id = :id").param("id", projectId).query(String.class).single();
                    Runnable delete = () -> deleteProject.execute(new DeleteProjectCommand(projectId, "UI"));

                    List<Outcome> outcomes = deleteFirst ? race(delete, call) : race(call, delete);

                    String label = contender.name() + (deleteFirst ? " after delete" : " before delete");
                    assertThat(outcomes).as(label).allMatch(Outcome::acceptable);
                    assertThat(rowsOf("project", projectId)).as(label).isZero();
                    assertThat(jdbc.sql("""
                            SELECT count(*) FROM outbox_event
                            WHERE project_key = :key AND published_at IS NULL AND event_type <> 'consent_revoked'""")
                            .param("key", projectKey).query(Integer.class).single()).as(label).isZero();
                }
            }
        }
        assertThat(retries.sqlStates()).doesNotContain(SqlErrors.DEADLOCK_DETECTED);
    }

    private UUID latestProject() {
        return jdbc.sql("SELECT id FROM project ORDER BY created_at DESC, id DESC LIMIT 1").query(UUID.class).single();
    }

    private long rowsOf(String table, UUID id) {
        return jdbc.sql("SELECT count(*) FROM " + table + " WHERE id = :id").param("id", id).query(Long.class).single();
    }

    /** null problem = success; NOT_FOUND = the project was already deleted; anything else fails the test. */
    private record Outcome(ProblemCode problem, Throwable unexpected) {
        boolean acceptable() {
            return unexpected == null && (problem == null || problem == ProblemCode.NOT_FOUND);
        }
    }

    /** Starts first, then second about 5 ms later, and waits for both. */
    private static List<Outcome> race(Runnable first, Runnable second) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch firstStarted = new CountDownLatch(1);
        try {
            Future<Outcome> a = pool.submit(() -> {
                firstStarted.countDown();
                return run(first);
            });
            firstStarted.await();
            Thread.sleep(5);
            Future<Outcome> b = pool.submit(() -> run(second));
            List<Outcome> outcomes = new ArrayList<>();
            outcomes.add(a.get(60, TimeUnit.SECONDS));
            outcomes.add(b.get(60, TimeUnit.SECONDS));
            return outcomes;
        } finally {
            pool.shutdownNow();
        }
    }

    private static Outcome run(Runnable call) {
        try {
            call.run();
            return new Outcome(null, null);
        } catch (UseCaseException e) {
            return new Outcome(e.problem(), null);
        } catch (RuntimeException e) {
            return new Outcome(null, e);
        }
    }
}
