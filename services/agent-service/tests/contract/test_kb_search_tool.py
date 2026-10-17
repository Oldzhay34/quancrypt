"""`kb_search` with real hits: every hit fits the tool contract and carries its source; the runtime versions filter
notes (D-227, guardrails-security section 4)."""

from __future__ import annotations

import pytest

from src.memory.long_term import Applicability, EmbeddingKnowledgeBase, KnowledgeChunk, KnowledgeDocument
from src.tools.base_tool import ToolContext
from src.tools.kb_search_tool import KbSearchTool
from src.tools.registry import ToolRegistry
from tests.support.embedding import DIMENSIONS, MODEL, BagOfWordsEmbedder
from tests.support.memory_fakes import InMemoryKnowledgeRepository
from tests.support.tools import TRACE, redactor, schemas


def note(
    doc_key: str, text: str, *, internal: bool, applicability: tuple[Applicability, ...] = ()
) -> KnowledgeDocument:
    return KnowledgeDocument(
        doc_key=doc_key,
        title=f"Not {doc_key}",
        source_url=None if internal else f"https://example.org/{doc_key}",
        source_type="INTERNAL" if internal else "STANDARD",
        version_tag=f"v-{doc_key}",
        language="tr",
        applicability=applicability,
        content_sha256="c" * 64,
        embedding_model=MODEL,
        chunk_chars=1200,
        chunk_overlap=100,
        chunks=(KnowledgeChunk(1, text, BagOfWordsEmbedder().embed([text]).vectors[0]),),
    )


@pytest.fixture
def registry() -> ToolRegistry:
    knowledge = EmbeddingKnowledgeBase(InMemoryKnowledgeRepository(), BagOfWordsEmbedder(), MODEL, DIMENSIONS, 5)
    knowledge.upsert_document(note("fips-203", "ml kem anahtar kapsulleme standardi", internal=False))
    knowledge.upsert_document(note("ic-oncelik", "oncelik mantigi ml kem tls", internal=True))
    knowledge.upsert_document(
        note("jep-496", "ml kem jdk api", internal=False, applicability=(Applicability("JAVA", min_version=(24, 0)),))
    )
    store = schemas()
    return ToolRegistry([KbSearchTool(knowledge, store)], {"planner": ("kb_search",)}, store, redactor())


def test_hits_fit_the_contract_and_carry_their_source(registry: ToolRegistry) -> None:
    output, _ = registry.call("kb_search", {"query": "ml kem", "k": 5}, ToolContext(trace_id=TRACE))  # output validated

    hits = {hit["doc_key"]: hit for hit in output["hits"]}
    assert set(hits) == {"fips-203", "ic-oncelik", "jep-496"}
    assert hits["fips-203"]["source_url"] == "https://example.org/fips-203"
    assert (hits["ic-oncelik"]["source_url"], hits["ic-oncelik"]["source_type"]) == (None, "INTERNAL")
    assert all(hit["version_tag"] and hit["title"] for hit in hits.values())
    distances = [hit["distance"] for hit in output["hits"]]
    assert distances == sorted(distances)


def test_a_note_for_a_newer_jdk_is_filtered_out_for_an_older_runtime(registry: ToolRegistry) -> None:
    output, _ = registry.call(
        "kb_search", {"query": "ml kem", "java_version": "17", "k": 5}, ToolContext(trace_id=TRACE)
    )

    assert "jep-496" not in {hit["doc_key"] for hit in output["hits"]}
