"""The knowledge base end to end: the real notes, the real embedding model (Ollama) and the real pgvector database.

Markers: `ollama` and `postgres`. Without Ollama or Docker these tests fail, they are not skipped (P4.2).
Drafts are indexed here on purpose (`include_draft`): the user approves the notes later, the search quality is
checked now.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.app.container import Container, build_container
from src.app.settings import CONFIG_DIR_ENV, load_settings
from src.memory.long_term import RuntimeVersions
from src.memory.memory_store import DatabaseConfig
from tests.support.postgres import PostgresInstance
from tests.support.scripts import SERVICE_ROOT, load_build_index

pytestmark = [pytest.mark.postgres, pytest.mark.ollama]

build_index = load_build_index()
RAW = SERVICE_ROOT / "data" / "raw"
JAVA_24_PLUS = {"kem-dem-kalibi", "jep-496-ml-kem", "jep-497-ml-dsa"}
ENTITY_TABLES = "kb_document, kb_document_applicability, kb_chunk"


def _point_environment_at(monkeypatch: pytest.MonkeyPatch, instance: PostgresInstance) -> None:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(SERVICE_ROOT / "config"))
    monkeypatch.setenv("AGENT_DB_URL", f"postgresql+psycopg://agent_db_app@127.0.0.1:{instance.port}/agent_db")
    monkeypatch.setenv(
        "AGENT_DB_MIGRATOR_URL", f"postgresql+psycopg://agent_db_migrator@127.0.0.1:{instance.port}/agent_db"
    )
    monkeypatch.setenv("AGENT_DB_APP_PASSWORD", instance.app_password)
    monkeypatch.setenv("AGENT_DB_MIGRATOR_PASSWORD", instance.migrator_password)
    for name in ("OLLAMA_BASE_URL", "LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)


def _empty_knowledge_tables(config: DatabaseConfig) -> None:
    engine = create_engine(make_url(config.migrator_url).set(password=config.migrator_password))
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {ENTITY_TABLES} CASCADE"))
    engine.dispose()


def _index_real_notes(container: Container) -> Any:
    settings = container.settings
    kb = settings.agents.memory.knowledge_base
    return build_index.index_notes(
        build_index.load_notes(RAW),
        container.knowledge_index,
        container.embeddings,
        embedding_model=settings.models.ollama.embedding_model,
        chunk_chars=kb.chunk_chars,
        chunk_overlap=kb.chunk_overlap,
        batch_size=kb.embed_batch,
        include_draft=True,
    )


@pytest.fixture(scope="module")
def indexed(
    postgres_instance: PostgresInstance, migrated_config: DatabaseConfig, monkeypatch_module: pytest.MonkeyPatch
) -> Iterator[Container]:
    """The real notes indexed once for the whole module."""
    _point_environment_at(monkeypatch_module, postgres_instance)
    _empty_knowledge_tables(migrated_config)
    container = build_container(load_settings())
    report = _index_real_notes(container)
    assert report.created == len(build_index.load_notes(RAW)), report.summary()
    yield container
    container.close()


@pytest.fixture(scope="module")
def monkeypatch_module() -> Iterator[pytest.MonkeyPatch]:
    patch = pytest.MonkeyPatch()
    yield patch
    patch.undo()


QUESTIONS = [
    (
        "Hibrit TLS için jdk.tls.namedGroups nasıl ayarlanır?",
        None,
        {"ayar-jdk-tls-anahtar-degisimi", "jep-527-hibrit-tls"},
    ),
    ("JDK 27'de varsayılan anahtar değişim grubu nedir?", None, {"jep-527-hibrit-tls"}),
    ("What is the default named group order for TLS 1.3 in JDK 27?", None, {"jep-527-hibrit-tls"}),
    ("Spring Boot'ta SSL bundle ile PEM sertifika nasıl tanımlanır?", None, {"spring-boot-ssl-paketleri"}),
    ("ETSI 014'te anahtar almak için hangi uç kullanılır?", None, {"etsi-qkd-014-uclar"}),
    ("QKD'yi yazılımla kurabilir miyiz?", None, {"qkd-sinirlari"}),
    ("RSA şifrelemenin yerine ML-KEM ile KEM-DEM nasıl yapılır?", 25, {"kem-dem-kalibi"}),
    ("RSA için 2035'ten sonra ne olacak?", None, {"nist-ir-8547-gecis-takvimi"}),
    ("Plan çıkarmadan önce kullanıcıya hangi sorular sorulur?", None, {"netlestirme-protokolu"}),
    ("JWT RS256 token'ları için hangi geçiş stratejisi öneriliyor?", None, {"strateji-tablosu"}),
    ("ML-KEM-768 açık anahtarı kaç bayttır?", None, {"saha-cihazlari-boyutlar"}),
    ("Which JEP adds ML-DSA to the JDK?", 25, {"jep-497-ml-dsa"}),
]


@pytest.mark.parametrize(("question", "java", "expected"), QUESTIONS)
def test_a_known_question_finds_its_note_among_the_first_three_results(
    indexed: Container, question: str, java: int | None, expected: set[str]
) -> None:
    hits = indexed.knowledge.search(question, RuntimeVersions(java_major=java), k=3)

    found = [h.doc_key for h in hits]
    assert expected & set(found), f"{question!r} -> {found}"
    assert all(h.title and h.version_tag for h in hits)


def test_every_result_carries_its_source_and_only_internal_notes_have_none(indexed: Container) -> None:
    hits = indexed.knowledge.search("hibrit anahtar değişimi ve geçiş stratejisi", RuntimeVersions(), k=10)

    assert hits
    for hit in hits:
        if hit.source_type == "INTERNAL":
            assert hit.source_url is None
        else:
            assert hit.source_url is not None and hit.source_url.startswith("https://")


def test_a_jdk_17_project_is_not_offered_the_notes_that_need_jdk_24(indexed: Container) -> None:
    question = "ML-KEM anahtar kapsülleme KEM-DEM JEP 496 JEP 497 ML-DSA"

    on_17 = {h.doc_key for h in indexed.knowledge.search(question, RuntimeVersions(java_major=17), k=50)}
    on_25 = {h.doc_key for h in indexed.knowledge.search(question, RuntimeVersions(java_major=25), k=50)}
    unknown = {h.doc_key for h in indexed.knowledge.search(question, RuntimeVersions(), k=50)}

    assert not on_17 & JAVA_24_PLUS
    assert on_25 >= JAVA_24_PLUS
    assert unknown >= JAVA_24_PLUS  # an unknown runtime does not filter (D-150)


def test_running_the_index_command_twice_changes_neither_the_database_nor_the_files(
    postgres_instance: PostgresInstance,
    migrated_config: DatabaseConfig,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _point_environment_at(monkeypatch, postgres_instance)
    _empty_knowledge_tables(migrated_config)
    raw = tmp_path / "raw"
    shutil.copytree(RAW, raw)
    arguments = [
        "--raw", str(raw), "--processed", str(tmp_path / "kb_chunks.jsonl"),
        "--manifest", str(tmp_path / "index_manifest.json"), "--include-draft",
    ]  # fmt: skip
    engine = create_engine(make_url(migrated_config.migrator_url).set(password=migrated_config.migrator_password))

    def snapshot() -> tuple[list[Any], list[Any], bytes, bytes]:
        with engine.connect() as connection:
            documents = connection.execute(
                text("SELECT id, doc_key, content_sha256, indexed_at FROM kb_document ORDER BY doc_key")
            ).all()
            chunks = connection.execute(
                text("SELECT id, document_id, ordinal, md5(text), md5(embedding::text) FROM kb_chunk ORDER BY id")
            ).all()
        return (
            list(documents),
            list(chunks),
            (tmp_path / "kb_chunks.jsonl").read_bytes(),
            (tmp_path / "index_manifest.json").read_bytes(),
        )

    assert build_index.main(arguments) == 0
    first_report = capsys.readouterr().out
    first = snapshot()
    assert build_index.main(arguments) == 0
    second_report = capsys.readouterr().out
    second = snapshot()
    engine.dispose()

    notes = len(build_index.load_notes(raw))
    assert f"created {notes}, updated 0, unchanged 0" in first_report
    assert f"created 0, updated 0, unchanged {notes}, retired 0" in second_report
    assert first == second
    assert len(first[0]) == notes and len(first[1]) >= notes


def test_the_index_command_refuses_a_broken_note_and_writes_nothing(
    postgres_instance: PostgresInstance,
    migrated_config: DatabaseConfig,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _point_environment_at(monkeypatch, postgres_instance)
    _empty_knowledge_tables(migrated_config)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "bozuk.md").write_text("frontmatter yok", encoding="utf-8")

    code = build_index.main(
        ["--raw", str(raw), "--processed", str(tmp_path / "c.jsonl"), "--manifest", str(tmp_path / "m.json")]
    )

    assert code == 2
    assert "bozuk.md" in capsys.readouterr().err
    assert not (tmp_path / "c.jsonl").exists() and not (tmp_path / "m.json").exists()
