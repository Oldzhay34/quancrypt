"""Contract of the memory ports (LSP): the in-memory double and the PostgreSQL adapter pass the same tests.

The PostgreSQL variants (marker `postgres`) start a pgvector container with the project's init scripts; without
Docker they
fail, they are not skipped (P4.2, D-231b).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.llm.null_provider import NullProvider
from src.memory.long_term import (
    Applicability,
    EmbeddingKnowledgeBase,
    EmptyKeepListError,
    Fingerprint,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeRepository,
    KnowledgeUnavailableError,
    RuntimeVersions,
)
from src.memory.memory_store import (
    Database,
    PostgresAuditLog,
    PostgresCheckpointStore,
    PostgresConversationMemory,
    PostgresKnowledgeRepository,
    PostgresOutboxRelayStore,
    PostgresScopeDecisionLog,
    utc_now,
)
from src.memory.short_term import (
    AuditLog,
    CheckpointStore,
    ConversationMemory,
    ConversationWindow,
    DuplicateRecordError,
    Evidence,
    IdempotencyConflictError,
    IdempotencyKey,
    InvalidRecordError,
    OutboxRelayStore,
    PendingEvent,
    ProjectKeyMismatchError,
    RunNotFoundError,
    RunNotRunningError,
    ScopeDecisionLog,
    ScopeDecisionRecord,
    SessionNotFoundError,
    StepRecord,
    ToolCallRecord,
)
from tests.support.embedding import DIMENSIONS, MODEL, BagOfWordsEmbedder
from tests.support.memory_fakes import (
    InMemoryAuditLog,
    InMemoryCheckpointStore,
    InMemoryConversationMemory,
    InMemoryKnowledgeRepository,
    InMemoryOutboxRelayStore,
    InMemoryScopeDecisionLog,
)

WINDOW = ConversationWindow(max_messages=3, token_budget=10, chars_per_token=4)
PROJECT = UUID("00000000-0000-0000-0000-0000000000a1")
KEY = "a" * 64
TRACE = "0123456789abcdef0123456789abcdef"
SHA = "b" * 64


def digest(seed: str) -> IdempotencyKey:
    return IdempotencyKey(key=f"key-{seed}", request_sha256=(seed.encode().hex() * 64)[:64])


# ---- conversation ----


class ConversationContract:
    """Subclasses provide the `memory` fixture."""

    @pytest.fixture
    def memory(self) -> ConversationMemory:
        raise NotImplementedError

    def test_a_created_session_can_be_read_back(self, memory: ConversationMemory) -> None:
        created = memory.create_session(PROJECT, KEY, "tr")

        assert created.replayed is False
        assert memory.get_session(created.session.id) == created.session
        assert (created.session.project_id, created.session.language) == (PROJECT, "tr")
        assert memory.get_session(uuid4()) is None

    def test_the_same_idempotency_key_replays_and_a_different_request_conflicts(
        self, memory: ConversationMemory
    ) -> None:
        first = memory.create_session(PROJECT, KEY, "tr", digest("a"))

        again = memory.create_session(PROJECT, KEY, "tr", digest("a"))

        assert (again.replayed, again.session.id) == (True, first.session.id)
        with pytest.raises(IdempotencyConflictError):
            memory.create_session(PROJECT, KEY, "en", IdempotencyKey("key-a", digest("b").request_sha256))

    def test_the_same_project_id_with_another_project_key_is_refused(self, memory: ConversationMemory) -> None:
        memory.create_session(PROJECT, KEY, "tr")

        with pytest.raises(ProjectKeyMismatchError):
            memory.create_session(PROJECT, "c" * 64, "tr")

    def test_a_project_key_must_be_64_hex_digits(self, memory: ConversationMemory) -> None:
        with pytest.raises(InvalidRecordError):
            memory.create_session(PROJECT, "short", "tr")

    def test_messages_get_gapless_ordinals_and_keep_their_evidence(self, memory: ConversationMemory) -> None:
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        evidence = (
            Evidence("KNOWLEDGE_BASE", "https://openjdk.org/jeps/496", "JEP 496"),
            Evidence("CODE_LOCATION", "A.java:3"),
        )

        first = memory.append_user_message(session, "soru")
        second = memory.append_assistant_message(session, "yanıt", evidence)
        third = memory.append_user_message(session, "ikinci soru")

        assert [first.ordinal, second.ordinal, third.ordinal] == [1, 2, 3]
        assert [first.role, second.role] == ["USER", "ASSISTANT"]
        page = memory.list_messages(session, 0, 50)
        assert [m.content for m in page.items] == ["soru", "yanıt", "ikinci soru"]
        assert page.items[1].evidence == evidence
        assert page.total == 3

    def test_list_messages_pages_oldest_first(self, memory: ConversationMemory) -> None:
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        for index in range(5):
            memory.append_user_message(session, f"m{index}")

        second_page = memory.list_messages(session, 1, 2)

        assert [m.content for m in second_page.items] == ["m2", "m3"]
        assert (second_page.page, second_page.size, second_page.total) == (1, 2, 5)
        with pytest.raises(InvalidRecordError):
            memory.list_messages(session, 0, 201)

    def test_the_conversation_window_keeps_the_newest_messages_within_the_budget(
        self, memory: ConversationMemory
    ) -> None:
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        for index in range(5):
            memory.append_user_message(session, f"{index}" * 20)  # 20 characters = 5 estimated tokens

        recent = memory.recent_messages(session)

        assert [m.ordinal for m in recent] == [4, 5]  # budget 10 tokens fits two of them
        assert all(m.evidence == () for m in recent)

    def test_the_newest_message_stays_even_when_it_alone_exceeds_the_budget(self, memory: ConversationMemory) -> None:
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        memory.append_user_message(session, "kısa")
        memory.append_user_message(session, "x" * 400)

        assert [m.ordinal for m in memory.recent_messages(session)] == [2]

    def test_text_with_a_nul_character_is_refused_before_the_database(self, memory: ConversationMemory) -> None:
        session = memory.create_session(PROJECT, KEY, "tr").session.id

        with pytest.raises(InvalidRecordError):
            memory.append_user_message(session, "a\x00b")
        with pytest.raises(InvalidRecordError):
            Evidence("CODE_LOCATION", "A.java\x00:3")
        with pytest.raises(InvalidRecordError):
            KnowledgeChunk(1, "metin\x00", (1.0,))

    def test_a_message_needs_content_and_a_session(self, memory: ConversationMemory) -> None:
        session = memory.create_session(PROJECT, KEY, "tr").session.id

        with pytest.raises(InvalidRecordError):
            memory.append_user_message(session, "")
        with pytest.raises(SessionNotFoundError):
            memory.append_user_message(uuid4(), "soru")

    def test_a_deleted_session_is_gone(self, memory: ConversationMemory) -> None:
        session = memory.create_session(PROJECT, KEY, "tr", digest("d")).session.id
        memory.append_user_message(session, "soru")

        memory.delete_session(session)

        assert memory.get_session(session) is None
        for call in (
            lambda: memory.append_user_message(session, "x"),
            lambda: memory.list_messages(session, 0, 10),
            lambda: memory.recent_messages(session),
            lambda: memory.delete_session(session),
        ):
            with pytest.raises(SessionNotFoundError):
                call()
        # The idempotency key of the deleted session is free again: the same request opens a new session.
        assert memory.create_session(PROJECT, KEY, "tr", digest("d")).replayed is False

    def test_deleting_the_project_data_removes_its_sessions_and_allows_a_fresh_start(
        self, memory: ConversationMemory
    ) -> None:
        one = memory.create_session(PROJECT, KEY, "tr").session.id
        two = memory.create_session(PROJECT, KEY, "en").session.id
        other = memory.create_session(UUID("00000000-0000-0000-0000-0000000000a2"), "d" * 64, "tr").session.id

        result = memory.delete_project_data(PROJECT)

        assert (result.sessions_deleted, result.project_ref_deleted) == (2, True)
        assert memory.get_session(one) is None and memory.get_session(two) is None
        assert memory.get_session(other) is not None
        assert memory.delete_project_data(PROJECT).project_ref_deleted is False
        # The same project registered again later (new project id, same key) is not blocked.
        memory.create_session(UUID("00000000-0000-0000-0000-0000000000a3"), KEY, "tr")


class TestInMemoryConversation(ConversationContract):
    @pytest.fixture
    def memory(self) -> ConversationMemory:
        return InMemoryConversationMemory(WINDOW)


@pytest.mark.postgres
class TestPostgresConversation(ConversationContract):
    @pytest.fixture
    def memory(self, database: Database) -> ConversationMemory:
        return PostgresConversationMemory(database, WINDOW, utc_now, uuid4)


# ---- audit ----


class AuditContract:
    @pytest.fixture
    def audit(self) -> AuditLog:
        raise NotImplementedError

    @staticmethod
    def step(run_id: UUID, ordinal: int = 1, **overrides: object) -> StepRecord:
        values: dict[str, object] = {
            "run_id": run_id,
            "ordinal": ordinal,
            "step_name": "ACT",
            "agent_code": "DISCOVERY",
            "status": "SUCCEEDED",
            "duration_ms": 12,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "started_at": datetime.now(UTC),
        }
        values.update(overrides)
        return StepRecord(**values)  # type: ignore[arg-type]

    def test_a_run_is_started_listed_by_trace_and_finished_once(self, audit: AuditLog) -> None:
        run_id = audit.start_run(None, "MESSAGE", TRACE)

        (listed,) = audit.list_runs_by_trace(TRACE)
        assert (listed.id, listed.status, listed.finished_at, listed.trigger) == (run_id, "RUNNING", None, "MESSAGE")
        audit.finish_run(run_id, "COMPLETED")
        (finished,) = audit.list_runs_by_trace(TRACE)
        assert finished.status == "COMPLETED" and finished.finished_at is not None
        with pytest.raises(RunNotRunningError):
            audit.finish_run(run_id, "FAILED")
        with pytest.raises(RunNotRunningError):
            audit.finish_run(uuid4(), "FAILED")

    def test_a_run_needs_an_existing_session_or_none(self, audit: AuditLog) -> None:
        with pytest.raises(SessionNotFoundError):
            audit.start_run(uuid4(), "MESSAGE", TRACE)

    def test_a_trace_id_must_be_32_hex_digits(self, audit: AuditLog) -> None:
        for bad in ("abc", "A" * 32, "ad.soyad_tc12345678901xxxxxxxxxx", ""):
            with pytest.raises(InvalidRecordError):
                audit.start_run(None, "MESSAGE", bad)

    def test_steps_and_tool_calls_are_recorded_and_a_step_cannot_be_recorded_twice(self, audit: AuditLog) -> None:
        run_id = audit.start_run(None, "INITIAL_SCAN", TRACE)
        calls = (
            ToolCallRecord(uuid4(), "ANALYZER", "SUCCEEDED", 40, datetime.now(UTC)),
            ToolCallRecord(uuid4(), "UNKNOWN", "DENIED", 1, datetime.now(UTC)),
        )

        audit.record_step(self.step(run_id, 1, tool_calls=calls))

        with pytest.raises(DuplicateRecordError):
            audit.record_step(self.step(run_id, 1))
        audit.record_step(self.step(run_id, 2, step_name="INPUT_GUARD", agent_code=None))

    def test_a_step_needs_an_existing_run(self, audit: AuditLog) -> None:
        with pytest.raises(RunNotFoundError):
            audit.record_step(self.step(uuid4()))

    def test_step_invariants_are_checked_before_anything_is_written(self) -> None:
        run_id = uuid4()
        with pytest.raises(InvalidRecordError):
            self.step(run_id, step_name="ROUTE", agent_code="SUPERVISOR")  # a workflow node carries no agent
        with pytest.raises(InvalidRecordError):
            self.step(run_id, step_name="PLAN", agent_code=None)  # a lifecycle step needs one
        with pytest.raises(InvalidRecordError):
            ToolCallRecord(uuid4(), "UNKNOWN", "SUCCEEDED", 1, datetime.now(UTC))  # an unregistered tool is only DENIED


class TestInMemoryAudit(AuditContract):
    @pytest.fixture
    def audit(self) -> AuditLog:
        return InMemoryAuditLog(InMemoryConversationMemory(WINDOW))


@pytest.mark.postgres
class TestPostgresAudit(AuditContract):
    @pytest.fixture
    def audit(self, database: Database) -> AuditLog:
        return PostgresAuditLog(database, utc_now, uuid4)


# ---- scope decisions ----


def classifier(**overrides: object) -> ScopeDecisionRecord:
    values: dict[str, object] = {
        "session_id": None,
        "decision": "ALLOW",
        "confidence": 0.91,
        "deciding_ring": "SCOPE_CLASSIFIER",
        "latency_ms": 12,
        "language": "tr",
    }
    values.update(overrides)
    return ScopeDecisionRecord(**values)  # type: ignore[arg-type]


class ScopeDecisionContract:
    @pytest.fixture
    def scope_log(self) -> tuple[ScopeDecisionLog, ConversationMemory]:
        raise NotImplementedError

    def test_the_event_is_written_only_with_consent_and_a_known_session(
        self, scope_log: tuple[ScopeDecisionLog, ConversationMemory]
    ) -> None:
        log, memory = scope_log
        session = memory.create_session(PROJECT, KEY, "tr").session.id

        assert log.record(classifier(session_id=session), warehouse_consent=True).event_written is True
        assert log.record(classifier(session_id=session), warehouse_consent=False).event_written is False
        assert log.record(classifier(session_id=None), warehouse_consent=True).event_written is False
        assert log.record(classifier(session_id=uuid4()), warehouse_consent=True).event_written is False

    def test_the_rule_filter_and_the_other_rings_carry_no_score(
        self, scope_log: tuple[ScopeDecisionLog, ConversationMemory]
    ) -> None:
        log, _ = scope_log

        log.record(classifier(deciding_ring="RULE_FILTER", confidence=None, decision="DENY"), warehouse_consent=False)
        log.record(classifier(deciding_ring="LLM_SELF_CHECK", confidence=None), warehouse_consent=False)
        log.record(classifier(deciding_ring="FAIL_CLOSED", confidence=None, decision="DENY"), warehouse_consent=False)

    def test_decision_invariants_are_checked(self) -> None:
        for bad in (
            {"deciding_ring": "RULE_FILTER", "confidence": 0.5},
            {"deciding_ring": "SCOPE_CLASSIFIER", "confidence": None},
            {"deciding_ring": "FAIL_CLOSED", "confidence": None, "decision": "ALLOW"},
            {"confidence": 1.5},
            {"latency_ms": -1},
        ):
            with pytest.raises(InvalidRecordError):
                classifier(**bad)


class TestInMemoryScopeDecisions(ScopeDecisionContract):
    @pytest.fixture
    def scope_log(self) -> tuple[ScopeDecisionLog, ConversationMemory]:
        memory = InMemoryConversationMemory(WINDOW)
        return InMemoryScopeDecisionLog(memory), memory


@pytest.mark.postgres
class TestPostgresScopeDecisions(ScopeDecisionContract):
    @pytest.fixture
    def scope_log(self, database: Database) -> tuple[ScopeDecisionLog, ConversationMemory]:
        return PostgresScopeDecisionLog(database, utc_now, uuid4), PostgresConversationMemory(
            database, WINDOW, utc_now, uuid4
        )


# ---- knowledge base ----


def document(
    doc_key: str,
    text: str,
    applicability: tuple[Applicability, ...] = (),
    *,
    sha: str = SHA,
    model: str = MODEL,
    chars: int = 1200,
) -> KnowledgeDocument:
    embedder = BagOfWordsEmbedder()
    return KnowledgeDocument(
        doc_key=doc_key,
        title=f"Not {doc_key}",
        source_url=None if doc_key.startswith("ic-") else f"https://example.org/{doc_key}",
        source_type="INTERNAL" if doc_key.startswith("ic-") else "STANDARD",
        version_tag=f"v-{doc_key}",
        language="tr",
        applicability=applicability,
        content_sha256=sha,
        embedding_model=model,
        chunk_chars=chars,
        chunk_overlap=100,
        chunks=(KnowledgeChunk(1, text, embedder.embed([text]).vectors[0]),),
    )


class KnowledgeContract:
    @pytest.fixture
    def repository(self) -> KnowledgeRepository:
        raise NotImplementedError

    @pytest.fixture
    def knowledge(self, repository: KnowledgeRepository) -> EmbeddingKnowledgeBase:
        return EmbeddingKnowledgeBase(repository, BagOfWordsEmbedder(), MODEL, DIMENSIONS, 5)

    def test_search_returns_the_closest_chunk_first_with_its_source(self, knowledge: EmbeddingKnowledgeBase) -> None:
        knowledge.upsert_document(document("mlkem", "ml kem anahtar kapsülleme java"))
        knowledge.upsert_document(document("ic-strateji", "p0 zayıf klasik kripto öncelik stratejisi"))
        knowledge.upsert_document(document("qkd", "qkd kuantum anahtar dağıtımı donanım"))

        hits = knowledge.search("ml kem anahtar kapsülleme", RuntimeVersions())

        assert hits[0].doc_key == "mlkem"
        assert (hits[0].title, hits[0].version_tag, hits[0].source_url) == (
            "Not mlkem",
            "v-mlkem",
            "https://example.org/mlkem",
        )
        assert hits[0].distance < hits[1].distance
        internal = knowledge.search("öncelik stratejisi", RuntimeVersions())[0]
        assert (internal.doc_key, internal.source_url, internal.source_type) == ("ic-strateji", None, "INTERNAL")

    def test_a_note_for_a_newer_java_is_not_suggested_to_an_older_runtime(
        self, knowledge: EmbeddingKnowledgeBase
    ) -> None:
        knowledge.upsert_document(document("jdk24", "ml kem jdk 24 api", (Applicability("JAVA", min_version=(24, 0)),)))
        knowledge.upsert_document(document("genel", "tls anahtar değişimi genel bilgi"))

        old = {h.doc_key for h in knowledge.search("ml kem jdk 24 api", RuntimeVersions(java_major=17))}
        new = {h.doc_key for h in knowledge.search("ml kem jdk 24 api", RuntimeVersions(java_major=25))}
        unknown = {h.doc_key for h in knowledge.search("ml kem jdk 24 api", RuntimeVersions())}

        assert old == {"genel"}
        assert new == {"jdk24", "genel"}
        assert unknown == {"jdk24", "genel"}  # an unknown runtime does not filter (D-150)

    def test_spring_boot_ranges_use_major_and_minor_and_both_bounds_are_inclusive(
        self, knowledge: EmbeddingKnowledgeBase
    ) -> None:
        rule = (Applicability("SPRING_BOOT", min_version=(3, 5), max_version=(3, 9)),)
        knowledge.upsert_document(document("boot", "ssl bundle pem sertifika", rule))

        def found(boot: tuple[int, int] | None) -> bool:
            return bool(knowledge.search("ssl bundle", RuntimeVersions(spring_boot=boot)))

        assert [found((3, 4)), found((3, 5)), found((3, 9)), found((4, 0)), found(None)] == [
            False,
            True,
            True,
            False,
            True,
        ]

    def test_an_unchanged_note_is_skipped_and_a_changed_one_is_updated(self, knowledge: EmbeddingKnowledgeBase) -> None:
        note = document("not", "ilk metin")

        assert knowledge.upsert_document(note).action == "created"
        assert knowledge.upsert_document(note).action == "unchanged"
        assert knowledge.upsert_document(note, force=True).action == "updated"  # --force rewrites a current note
        assert knowledge.is_current(Fingerprint("not", SHA, MODEL, 1200, 100)) is True
        assert knowledge.is_current(Fingerprint("not", SHA, MODEL, 800, 100)) is False  # another chunking
        assert knowledge.upsert_document(document("not", "ikinci metin", sha="c" * 64)).action == "updated"
        assert knowledge.upsert_document(document("not", "ikinci metin", sha="c" * 64, chars=800)).action == "updated"

    def test_only_documents_of_the_current_model_are_searched(self, knowledge: EmbeddingKnowledgeBase) -> None:
        knowledge.upsert_document(document("eski", "ml kem anahtar", model="old-model"))

        assert knowledge.search("ml kem anahtar", RuntimeVersions()) == ()

    def test_retired_documents_disappear_and_an_empty_keep_list_is_refused(
        self, knowledge: EmbeddingKnowledgeBase
    ) -> None:
        knowledge.upsert_document(document("a", "alfa metin"))
        knowledge.upsert_document(document("b", "beta metin"))

        assert knowledge.retire_documents(["a"]) == 1
        assert {h.doc_key for h in knowledge.search("metin", RuntimeVersions())} == {"a"}
        with pytest.raises(EmptyKeepListError):
            knowledge.retire_documents([])
        assert {h.doc_key for h in knowledge.search("metin", RuntimeVersions())} == {"a"}

    def test_search_is_unavailable_without_an_embedding_model_and_validates_its_input(
        self, repository: KnowledgeRepository
    ) -> None:
        offline = EmbeddingKnowledgeBase(repository, NullProvider(), MODEL, DIMENSIONS, 5)

        with pytest.raises(KnowledgeUnavailableError):
            offline.search("soru", RuntimeVersions())
        online = EmbeddingKnowledgeBase(repository, BagOfWordsEmbedder(), MODEL, DIMENSIONS, 5)
        with pytest.raises(InvalidRecordError):
            online.search("   ", RuntimeVersions())
        with pytest.raises(InvalidRecordError):
            online.search("soru", RuntimeVersions(), k=0)


class TestInMemoryKnowledge(KnowledgeContract):
    @pytest.fixture
    def repository(self) -> KnowledgeRepository:
        return InMemoryKnowledgeRepository()


@pytest.mark.postgres
class TestPostgresKnowledge(KnowledgeContract):
    @pytest.fixture
    def repository(self, database: Database) -> KnowledgeRepository:
        return PostgresKnowledgeRepository(database, utc_now, uuid4)


# A type check that the factories above really produce the ports (mypy verifies the assignments).
_FACTORIES: tuple[Callable[..., object], ...] = (
    InMemoryConversationMemory,
    InMemoryAuditLog,
    InMemoryScopeDecisionLog,
    InMemoryKnowledgeRepository,
)


# ---- graph checkpoints (P4.6, D-253) ----


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _ids() -> tuple[UUID, UUID, UUID]:
    # uuid6-like order: the later id compares greater (byte order), as LangGraph's checkpoint ids do.
    return (
        UUID("1f1cb0a7-7994-6389-8000-000000000001"),
        UUID("1f1cb0a7-7994-6389-8000-000000000002"),
        UUID("1f1cb0a7-7994-6389-8000-000000000003"),
    )


class CheckpointContract:
    @pytest.fixture
    def stores(self) -> tuple[CheckpointStore, ConversationMemory, _Clock]:
        raise NotImplementedError

    def test_a_checkpoint_round_trips_per_session(
        self, stores: tuple[CheckpointStore, ConversationMemory, _Clock]
    ) -> None:
        store, memory, _ = stores
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        first, _, _ = _ids()

        assert store.get(session) is None
        assert store.put(session, first, "msgpack", b"\x81\xa1a\x01") is True
        stored = store.get(session)
        assert stored is not None
        assert (stored.checkpoint_id, stored.state_type, stored.state) == (first, "msgpack", b"\x81\xa1a\x01")

    def test_an_older_checkpoint_never_overwrites_a_newer_one(
        self, stores: tuple[CheckpointStore, ConversationMemory, _Clock]
    ) -> None:
        store, memory, _ = stores
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        first, second, third = _ids()

        assert store.put(session, second, "msgpack", b"new") is True
        assert store.put(session, first, "msgpack", b"old") is False
        assert store.put(session, second, "msgpack", b"same") is False
        stored = store.get(session)
        assert stored is not None and stored.state == b"new"
        assert store.put(session, third, "msgpack", b"newer") is True

    def test_a_deleted_session_has_no_checkpoint_and_refuses_one(
        self, stores: tuple[CheckpointStore, ConversationMemory, _Clock]
    ) -> None:
        store, memory, _ = stores
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        first, second, _ = _ids()
        store.put(session, first, "msgpack", b"x")

        memory.delete_session(session)

        assert store.get(session) is None
        with pytest.raises(SessionNotFoundError):
            store.put(session, second, "msgpack", b"y")

    def test_only_msgpack_up_to_64_kib_is_stored(
        self, stores: tuple[CheckpointStore, ConversationMemory, _Clock]
    ) -> None:
        store, memory, _ = stores
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        first, _, _ = _ids()
        for state_type, state in (("pickle", b"x"), ("msgpack", b""), ("msgpack", b"x" * 65537)):
            with pytest.raises(InvalidRecordError):
                store.put(session, first, state_type, state)
        assert store.put(session, first, "msgpack", b"x" * 65536) is True

    def test_checkpoints_idle_for_24_hours_are_purged_and_the_chat_stays(
        self, stores: tuple[CheckpointStore, ConversationMemory, _Clock]
    ) -> None:
        store, memory, clock = stores
        old = memory.create_session(PROJECT, KEY, "tr").session.id
        fresh = memory.create_session(PROJECT, KEY, "tr").session.id
        memory.append_user_message(old, "merhaba")
        first, second, _ = _ids()
        store.put(old, first, "msgpack", b"old")
        clock.now = clock.now + timedelta(hours=23)
        store.put(fresh, second, "msgpack", b"fresh")
        clock.now = clock.now + timedelta(hours=2)

        assert store.purge_idle() == 1
        assert store.get(old) is None
        assert store.get(fresh) is not None
        assert memory.list_messages(old, 0, 10).total == 1


class TestInMemoryCheckpoints(CheckpointContract):
    @pytest.fixture
    def stores(self) -> tuple[CheckpointStore, ConversationMemory, _Clock]:
        clock = _Clock()
        memory = InMemoryConversationMemory(WINDOW)
        return InMemoryCheckpointStore(memory, clock), memory, clock


@pytest.mark.postgres
class TestPostgresCheckpoints(CheckpointContract):
    @pytest.fixture
    def stores(self, database: Database) -> tuple[CheckpointStore, ConversationMemory, _Clock]:
        clock = _Clock()
        return (
            PostgresCheckpointStore(database, clock),
            PostgresConversationMemory(database, WINDOW, clock, uuid4),
            clock,
        )


# ---- outbox relay store (P4.6, D-232a, D-252g) ----


def _decision(session: UUID) -> ScopeDecisionRecord:
    return ScopeDecisionRecord(session, "DENY", None, "RULE_FILTER", 2, "tr")


class OutboxRelayContract:
    @pytest.fixture
    def relay(self) -> tuple[OutboxRelayStore, ScopeDecisionLog, ConversationMemory]:
        raise NotImplementedError

    def test_pending_events_come_oldest_first_with_their_envelope_fields(
        self, relay: tuple[OutboxRelayStore, ScopeDecisionLog, ConversationMemory]
    ) -> None:
        store, log, memory = relay
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        for _ in range(3):
            log.record(_decision(session), warehouse_consent=True)

        pending = store.pending(10)

        assert len(pending) == 3
        assert [e.occurred_at for e in pending] == sorted(e.occurred_at for e in pending)
        assert {(e.event_type, e.schema_version, e.project_key) for e in pending} == {("scope_decision", 1, KEY)}
        assert pending[0].payload["deciding_ring"] == "RULE_FILTER"
        assert len(store.pending(2)) == 2

    def test_marking_is_idempotent_and_discard_removes_only_pending_events(
        self, relay: tuple[OutboxRelayStore, ScopeDecisionLog, ConversationMemory]
    ) -> None:
        store, log, memory = relay
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        for _ in range(3):
            log.record(_decision(session), warehouse_consent=True)
        first, second, third = store.pending(10)
        sent: list[tuple[PendingEvent, ...]] = []

        assert store.publish_locked([first.id], sent.append) == 1
        assert store.publish_locked([first.id], sent.append) == 0  # already sent: not sent again
        assert [[e.id for e in batch] for batch in sent] == [[first.id]]
        assert store.discard([first.id, second.id]) == 1  # the sent one stays
        assert [e.id for e in store.pending(10)] == [third.id]
        assert store.publish_locked([], sent.append) == 0 and store.discard([]) == 0
        assert len(sent) == 1  # `send` is not called when nothing is left

    def test_a_failing_send_marks_nothing_and_a_deleted_event_is_not_sent(
        self, relay: tuple[OutboxRelayStore, ScopeDecisionLog, ConversationMemory]
    ) -> None:
        store, log, memory = relay
        session = memory.create_session(PROJECT, KEY, "tr").session.id
        for _ in range(2):
            log.record(_decision(session), warehouse_consent=True)
        first, second = store.pending(10)

        def fail(_: tuple[PendingEvent, ...]) -> None:
            raise RuntimeError("ingest down")

        with pytest.raises(RuntimeError):
            store.publish_locked([first.id], fail)
        assert [e.id for e in store.pending(10)] == [first.id, second.id]

        store.discard([second.id])
        sent: list[tuple[PendingEvent, ...]] = []
        assert store.publish_locked([first.id, second.id], sent.append) == 1
        assert [[e.id for e in batch] for batch in sent] == [[first.id]]

    def test_project_ids_resolve_a_key_and_the_batch_is_bounded(
        self, relay: tuple[OutboxRelayStore, ScopeDecisionLog, ConversationMemory]
    ) -> None:
        store, _, memory = relay
        memory.create_session(PROJECT, KEY, "tr")

        assert store.project_ids(KEY) == (PROJECT,)
        assert store.project_ids("c" * 64) == ()
        for limit in (0, 201):
            with pytest.raises(InvalidRecordError):
                store.pending(limit)


class TestInMemoryOutboxRelay(OutboxRelayContract):
    @pytest.fixture
    def relay(self) -> tuple[OutboxRelayStore, ScopeDecisionLog, ConversationMemory]:
        memory = InMemoryConversationMemory(WINDOW)
        log = InMemoryScopeDecisionLog(memory)
        return InMemoryOutboxRelayStore(memory, log), log, memory


@pytest.mark.postgres
class TestPostgresOutboxRelay(OutboxRelayContract):
    @pytest.fixture
    def relay(self, database: Database) -> tuple[OutboxRelayStore, ScopeDecisionLog, ConversationMemory]:
        return (
            PostgresOutboxRelayStore(database, utc_now),
            PostgresScopeDecisionLog(database, utc_now, uuid4),
            PostgresConversationMemory(database, WINDOW, utc_now, uuid4),
        )
