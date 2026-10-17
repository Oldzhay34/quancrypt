"""`scripts/build_index.py`: frontmatter rules, range parsing, selection of approved notes and idempotent output."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from src.memory.long_term import EmbeddingKnowledgeBase, RuntimeVersions
from tests.support.embedding import DIMENSIONS, MODEL, BagOfWordsEmbedder
from tests.support.memory_fakes import InMemoryKnowledgeRepository
from tests.support.scripts import load_build_index

build_index = load_build_index()

GOOD = """---
id: ornek-not
title: "Örnek not: başlık"
source_url: "https://openjdk.org/jeps/496"
source_type: JEP
version_tag: "JDK 24"
applies_to:
  java: ">=24"
language: tr
status: approved
---

ML-KEM anahtar kapsülleme için kullanılır.
"""


def write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def knowledge() -> tuple[EmbeddingKnowledgeBase, InMemoryKnowledgeRepository]:
    repository = InMemoryKnowledgeRepository()
    return EmbeddingKnowledgeBase(repository, BagOfWordsEmbedder(), MODEL, DIMENSIONS, 5), repository


def run(notes: list[Any], kb: EmbeddingKnowledgeBase, **overrides: Any) -> Any:
    options: dict[str, Any] = {"embedding_model": MODEL, "chunk_chars": 400, "chunk_overlap": 40, "batch_size": 4}
    options.update(overrides)
    return build_index.index_notes(notes, kb, BagOfWordsEmbedder(), **options)


def test_a_good_note_parses_with_its_range_and_a_whole_file_digest(tmp_path: Path) -> None:
    path = write(tmp_path, "ornek-not.md", GOOD)

    note = build_index.parse_note(path)

    assert (note.doc_key, note.title, note.source_type, note.status) == (
        "ornek-not",
        "Örnek not: başlık",
        "JEP",
        "approved",
    )
    assert [(a.component, a.min_version, a.max_version) for a in note.applicability] == [("JAVA", (24, 0), None)]
    assert note.body == "ML-KEM anahtar kapsülleme için kullanılır."
    assert len(note.sha256) == 64
    changed = write(tmp_path, "ornek-not.md", GOOD.replace('"JDK 24"', '"JDK 25"'))
    assert build_index.parse_note(changed).sha256 != note.sha256  # the frontmatter is part of the digest


MUTATIONS: list[tuple[Callable[[str], str], str]] = [
    (lambda t: t.replace("id: ornek-not", "id: baska-ad"), "must equal the file name"),
    (lambda t: t.replace("source_type: JEP", "source_type: BLOG"), "source_type"),
    (lambda t: t.replace("language: tr", "language: de"), "language"),
    (lambda t: t.replace("status: approved", "status: reviewed"), "status"),
    (lambda t: t.replace('source_url: "https://openjdk.org/jeps/496"', "source_url: null"), "only INTERNAL"),
    (lambda t: t.replace("https://openjdk.org/jeps/496", "http://openjdk.org/jeps/496"), "https"),
    (lambda t: t.replace("status: approved\n", ""), "missing keys"),
    (lambda t: t.replace("language: tr", "language: tr\nextra: 1"), "unknown keys"),
    (lambda t: t.replace('">=24"', '"24+"'), "cannot read the range"),
    (lambda t: t.replace("java:", "python:"), "supports `java`"),
    (lambda t: t.replace('">=24"', '">=30,<=24"'), "exceeds"),
    (lambda t: t.replace("ML-KEM anahtar kapsülleme için kullanılır.", ""), "no text"),
    (lambda t: t.replace("---\nid:", "id:", 1), "no frontmatter"),
    (lambda t: t.replace('version_tag: "JDK 24"', 'version_tag: "' + "x" * 65 + '"'), "version_tag"),
]


@pytest.mark.parametrize(("mutation", "reason"), MUTATIONS)
def test_a_note_that_breaks_a_rule_is_rejected_with_the_reason(
    tmp_path: Path, mutation: Callable[[str], str], reason: str
) -> None:
    path = write(tmp_path, "ornek-not.md", mutation(GOOD))

    with pytest.raises(build_index.NoteError, match=reason):
        build_index.parse_note(path)


def test_an_internal_note_may_leave_the_source_empty(tmp_path: Path) -> None:
    text = GOOD.replace("source_type: JEP", "source_type: INTERNAL").replace(
        'source_url: "https://openjdk.org/jeps/496"', "source_url: null"
    )

    assert build_index.parse_note(write(tmp_path, "ornek-not.md", text)).source_url is None


def test_ranges_with_both_bounds_and_spring_boot_minor_versions() -> None:
    rules = build_index.parse_applies_to({"java": ">=17,<=21", "spring_boot": ">=3.5"}, "x.md")

    assert [(r.component, r.min_version, r.max_version) for r in rules] == [
        ("JAVA", (17, 0), (21, 0)),
        ("SPRING_BOOT", (3, 5), None),
    ]
    assert build_index.parse_applies_to({}, "x.md") == ()
    assert build_index.parse_applies_to(None, "x.md") == ()


def test_all_broken_notes_are_reported_together(tmp_path: Path) -> None:
    write(tmp_path, "bir.md", GOOD.replace("id: ornek-not", "id: x"))
    write(tmp_path, "iki.md", "no frontmatter")

    with pytest.raises(build_index.NoteError) as error:
        build_index.load_notes(tmp_path)

    assert "bir.md" in str(error.value) and "iki.md" in str(error.value)


def test_only_approved_notes_are_indexed_and_the_second_run_changes_nothing(tmp_path: Path) -> None:
    write(tmp_path, "onayli.md", GOOD.replace("ornek-not", "onayli"))
    write(tmp_path, "taslak.md", GOOD.replace("ornek-not", "taslak").replace("status: approved", "status: draft"))
    notes = build_index.load_notes(tmp_path)
    kb, repository = knowledge()

    first = run(notes, kb)
    second = run(notes, kb)

    assert (first.created, first.unchanged, first.drafts_skipped) == (1, 0, 1)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 1)
    assert set(repository.documents) == {"onayli"}
    assert [h.doc_key for h in kb.search("ML-KEM kapsülleme", RuntimeVersions(java_major=25))] == ["onayli"]
    assert kb.search("ML-KEM kapsülleme", RuntimeVersions(java_major=17)) == ()  # the note applies from JDK 24


def test_a_note_that_is_no_longer_approved_is_retired(tmp_path: Path) -> None:
    write(tmp_path, "bir.md", GOOD.replace("ornek-not", "bir"))
    write(tmp_path, "iki.md", GOOD.replace("ornek-not", "iki"))
    kb, repository = knowledge()
    run(build_index.load_notes(tmp_path), kb)
    write(tmp_path, "iki.md", GOOD.replace("ornek-not", "iki").replace("status: approved", "status: draft"))

    report = run(build_index.load_notes(tmp_path), kb)

    assert report.retired == 1
    assert set(repository.documents) == {"bir"}


def test_include_draft_indexes_drafts_and_force_re_embeds(tmp_path: Path) -> None:
    write(tmp_path, "taslak.md", GOOD.replace("ornek-not", "taslak").replace("status: approved", "status: draft"))
    notes = build_index.load_notes(tmp_path)
    kb, _ = knowledge()

    included = run(notes, kb, include_draft=True)
    forced = run(notes, kb, include_draft=True, force=True)

    assert (included.created, included.drafts_skipped) == (1, 0)
    assert forced.updated == 1 and forced.unchanged == 0


def test_a_changed_chunking_or_model_re_indexes_the_note(tmp_path: Path) -> None:
    write(tmp_path, "bir.md", GOOD.replace("ornek-not", "bir"))
    notes = build_index.load_notes(tmp_path)
    kb, _ = knowledge()
    run(notes, kb)

    assert run(notes, kb, chunk_chars=500).updated == 1
    assert run(notes, kb, chunk_chars=500).unchanged == 1
    assert run(notes, kb, chunk_chars=500, embedding_model="another-model").updated == 1


def test_the_artifacts_are_deterministic_and_carry_no_vectors_or_times(tmp_path: Path) -> None:
    write(tmp_path, "b-not.md", GOOD.replace("ornek-not", "b-not"))
    write(tmp_path, "a-not.md", GOOD.replace("ornek-not", "a-not"))
    notes = build_index.load_notes(tmp_path)
    kb, _ = knowledge()
    report = run(notes, kb)
    options = {"embedding_model": MODEL, "dimensions": DIMENSIONS, "chunk_chars": 400, "chunk_overlap": 40}
    chunks_path, manifest_path = tmp_path / "out" / "chunks.jsonl", tmp_path / "out" / "manifest.json"

    build_index.write_artifacts(report, chunks_path, manifest_path, **options)
    first = (chunks_path.read_bytes(), manifest_path.read_bytes())
    build_index.write_artifacts(report, chunks_path, manifest_path, **options)
    second = (chunks_path.read_bytes(), manifest_path.read_bytes())

    assert first == second
    manifest = json.loads(first[1])
    assert [d["doc_key"] for d in manifest["documents"]] == ["a-not", "b-not"]
    assert manifest["embedding_dimensions"] == DIMENSIONS and manifest["chunk_chars"] == 400
    rows = [json.loads(line) for line in first[0].decode().splitlines()]
    assert [r["doc_key"] for r in rows] == ["a-not", "b-not"]
    assert set(rows[0]) == {"doc_key", "ordinal", "text"}
