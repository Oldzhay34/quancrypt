#!/usr/bin/env python3
"""Builds the knowledge-base index from `data/raw/*.md` (P4.2).

Reads the notes, validates their frontmatter, splits the approved ones into chunks, embeds the chunks with the
configured embedding model and writes them to agent_db (`kb_document`, `kb_chunk`) idempotently. It also writes two
deterministic files: `data/processed/kb_chunks.jsonl` (the chunks without vectors) and
`data/vector_db/index_manifest.json`
(model, chunking and one entry per note). Running it twice gives the same database rows (a note whose file, model and
chunking are unchanged is skipped) and the same two files.

Only notes with `status: approved` are indexed; `--include-draft` adds drafts (tests and review only). Notes that are
not
indexed any more (draft, deleted) are retired from the database. Changing the embedding model, its dimensions or the
chunking re-embeds every note automatically; after a dimension change run the migration first (`vector(768)`) and then
`make index` (it passes `--force`).

Usage (from services/agent-service, with AGENT_DB_* passwords in the environment):
  python scripts/build_index.py [--force] [--include-draft]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.llm.provider import EmbeddingProvider, LLMError
from src.memory.long_term import (
    Applicability,
    EmptyKeepListError,
    Fingerprint,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndex,
    chunk_text,
)

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_TYPES = ("STANDARD", "JEP", "VENDOR_DOC", "SPECIFICATION", "GOVERNMENT_GUIDANCE", "INTERNAL")
LANGUAGES = ("tr", "en")
STATUSES = ("draft", "approved")
REQUIRED_KEYS = ("id", "title", "source_url", "source_type", "version_tag", "applies_to", "language", "status")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_BOUND = re.compile(r"\s*(>=|<=)\s*([0-9]+(?:\.[0-9]+)?)\s*")


class NoteError(ValueError):
    """A note that cannot be indexed; the message names the file and the reason."""


@dataclass(frozen=True)
class Note:
    doc_key: str
    title: str
    source_url: str | None
    source_type: str
    version_tag: str
    language: str
    applicability: tuple[Applicability, ...]
    status: str
    body: str
    sha256: str


@dataclass
class IndexReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    retired: int = 0
    drafts_skipped: int = 0
    notes: list[Note] = field(default_factory=list)
    chunks: dict[str, list[str]] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"created {self.created}, updated {self.updated}, unchanged {self.unchanged}, retired {self.retired}, "
            f"drafts skipped {self.drafts_skipped} (indexed notes: {len(self.notes)})"
        )


# ---- notes ----


def parse_applies_to(value: Any, where: str) -> tuple[Applicability, ...]:
    """`applies_to: {java: ">=24", spring_boot: ">=3.5,<=3.9"}`; both bounds are inclusive."""
    if value in (None, {}):
        return ()
    if not isinstance(value, dict):
        raise NoteError(f"{where}: applies_to must be a mapping of component to range")
    rules: list[Applicability] = []
    for name, spec in value.items():
        if name not in ("java", "spring_boot") or not isinstance(spec, str):
            raise NoteError(f"{where}: applies_to supports `java` and `spring_boot` with a range string")
        lower: tuple[int, int] | None = None
        upper: tuple[int, int] | None = None
        rest = spec.strip()
        for part in (p for p in rest.split(",") if p.strip()):
            match = _BOUND.fullmatch(part)
            if match is None:
                raise NoteError(f"{where}: cannot read the range `{spec}` (use >=N and <=N, comma separated)")
            major, _, minor = match.group(2).partition(".")
            bound = (int(major), int(minor or 0))
            if match.group(1) == ">=":
                lower = bound
            else:
                upper = bound
        try:
            rules.append(Applicability("JAVA" if name == "java" else "SPRING_BOOT", lower, upper))
        except ValueError as exc:
            raise NoteError(f"{where}: {exc}") from exc
    return tuple(rules)


def parse_note(path: Path) -> Note:
    where = path.name
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NoteError(f"{where}: not UTF-8") from exc
    match = _FRONTMATTER.match(text.replace("\r\n", "\n"))
    if match is None:
        raise NoteError(f"{where}: no frontmatter (the file must start with a --- block)")
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise NoteError(f"{where}: the frontmatter is not valid YAML") from exc
    if not isinstance(meta, dict):
        raise NoteError(f"{where}: the frontmatter must be a mapping")
    missing = [key for key in REQUIRED_KEYS if key not in meta]
    unknown = [key for key in meta if key not in REQUIRED_KEYS]
    if missing or unknown:
        raise NoteError(f"{where}: missing keys {missing}, unknown keys {unknown}")
    if meta["id"] != path.stem:
        raise NoteError(f"{where}: id `{meta['id']}` must equal the file name `{path.stem}`")
    if meta["source_type"] not in SOURCE_TYPES:
        raise NoteError(f"{where}: source_type must be one of {SOURCE_TYPES}")
    if meta["language"] not in LANGUAGES:
        raise NoteError(f"{where}: language must be one of {LANGUAGES}")
    if meta["status"] not in STATUSES:
        raise NoteError(f"{where}: status must be one of {STATUSES}")
    url = meta["source_url"]
    if url is None and meta["source_type"] != "INTERNAL":
        raise NoteError(f"{where}: only INTERNAL notes may leave source_url empty")
    if url is not None and not (isinstance(url, str) and re.fullmatch(r"https://\S+", url) and len(url) <= 1024):
        raise NoteError(f"{where}: source_url must be an https address")
    for key, limit in (("title", 300), ("version_tag", 64)):
        if not isinstance(meta[key], str) or not meta[key].strip() or len(meta[key]) > limit:
            raise NoteError(f"{where}: {key} must be a text of 1 to {limit} characters")
    body = match.group(2).strip()
    if not body:
        raise NoteError(f"{where}: the note has no text")
    return Note(
        doc_key=meta["id"],
        title=meta["title"],
        source_url=url,
        source_type=meta["source_type"],
        version_tag=meta["version_tag"],
        language=meta["language"],
        applicability=parse_applies_to(meta["applies_to"], where),
        status=meta["status"],
        body=body,
        # The whole file, frontmatter included: a change of source, version or range re-indexes the note.
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_notes(raw_dir: Path) -> list[Note]:
    paths = sorted(raw_dir.glob("*.md"))
    notes: list[Note] = []
    errors: list[str] = []
    for path in paths:
        try:
            notes.append(parse_note(path))
        except NoteError as exc:
            errors.append(str(exc))
    if errors:
        raise NoteError("\n".join(errors))
    return notes


# ---- indexing ----


def embedding_input(note: Note, chunk: str) -> str:
    """The title leads the embedded text (a short chunk is better found by its note's topic); the stored text is the
    chunk."""
    return f"{note.title}\n\n{chunk}"


def index_notes(
    notes: Sequence[Note],
    knowledge: KnowledgeIndex,
    embeddings: EmbeddingProvider,
    *,
    embedding_model: str,
    chunk_chars: int,
    chunk_overlap: int,
    batch_size: int,
    force: bool = False,
    include_draft: bool = False,
) -> IndexReport:
    report = IndexReport()
    selected = [n for n in notes if n.status == "approved" or include_draft]
    report.drafts_skipped = len(notes) - len(selected)
    for note in selected:
        pieces = chunk_text(note.body, chunk_chars, chunk_overlap)
        report.notes.append(note)
        report.chunks[note.doc_key] = pieces
        fingerprint = Fingerprint(note.doc_key, note.sha256, embedding_model, chunk_chars, chunk_overlap)
        if not force and knowledge.is_current(fingerprint):
            report.unchanged += 1
            continue
        vectors: list[tuple[float, ...]] = []
        for start in range(0, len(pieces), batch_size):
            batch = [embedding_input(note, p) for p in pieces[start : start + batch_size]]
            vectors.extend(embeddings.embed(batch).vectors)
        document = KnowledgeDocument(
            doc_key=note.doc_key,
            title=note.title,
            source_url=note.source_url,
            source_type=note.source_type,  # type: ignore[arg-type]
            version_tag=note.version_tag,
            language=note.language,  # type: ignore[arg-type]
            applicability=note.applicability,
            content_sha256=note.sha256,
            embedding_model=embedding_model,
            chunk_chars=chunk_chars,
            chunk_overlap=chunk_overlap,
            chunks=tuple(KnowledgeChunk(i, p, v) for i, (p, v) in enumerate(zip(pieces, vectors, strict=True), 1)),
        )
        action = knowledge.upsert_document(document, force=force).action
        if action == "created":
            report.created += 1
        elif action == "updated":
            report.updated += 1
        else:
            report.unchanged += 1
    if selected:
        report.retired = knowledge.retire_documents([n.doc_key for n in selected])
    return report


def write_artifacts(
    report: IndexReport,
    processed: Path,
    manifest: Path,
    *,
    embedding_model: str,
    dimensions: int,
    chunk_chars: int,
    chunk_overlap: int,
) -> None:
    """Deterministic: sorted, no timestamps, so a second run changes nothing."""
    processed.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"doc_key": n.doc_key, "ordinal": i, "text": piece}, ensure_ascii=False, sort_keys=True)
        for n in sorted(report.notes, key=lambda n: n.doc_key)
        for i, piece in enumerate(report.chunks[n.doc_key], 1)
    ]
    processed.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    document = {
        "embedding_model": embedding_model,
        "embedding_dimensions": dimensions,
        "chunk_chars": chunk_chars,
        "chunk_overlap": chunk_overlap,
        "documents": [
            {
                "doc_key": n.doc_key,
                "title": n.title,
                "source_type": n.source_type,
                "version_tag": n.version_tag,
                "status": n.status,
                "content_sha256": n.sha256,
                "chunks": len(report.chunks[n.doc_key]),
            }
            for n in sorted(report.notes, key=lambda n: n.doc_key)
        ],
    }
    manifest.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


# ---- command line ----


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index data/raw/*.md into agent_db (idempotent).")
    parser.add_argument("--raw", type=Path, default=SERVICE_ROOT / "data" / "raw")
    parser.add_argument("--processed", type=Path, default=SERVICE_ROOT / "data" / "processed" / "kb_chunks.jsonl")
    parser.add_argument("--manifest", type=Path, default=SERVICE_ROOT / "data" / "vector_db" / "index_manifest.json")
    parser.add_argument("--force", action="store_true", help="re-embed every note even if it is current")
    parser.add_argument(
        "--include-draft", action="store_true", help="also index notes with status: draft (tests, review)"
    )
    args = parser.parse_args(argv)

    # Imported here so that the pure functions above can be tested without building the application.
    from src.app.container import build_container
    from src.app.settings import load_settings

    try:
        notes = load_notes(args.raw)
    except NoteError as exc:
        print(f"Invalid notes:\n{exc}", file=sys.stderr)
        return 2
    if not notes:
        print(f"No notes in {args.raw}", file=sys.stderr)
        return 2
    settings = load_settings()
    container = build_container(settings)
    try:
        container.startup()
        kb = settings.agents.memory.knowledge_base
        ollama = settings.models.ollama
        try:
            report = index_notes(
                notes,
                container.knowledge_index,
                container.embeddings,
                embedding_model=ollama.embedding_model,
                chunk_chars=kb.chunk_chars,
                chunk_overlap=kb.chunk_overlap,
                batch_size=kb.embed_batch,
                force=args.force,
                include_draft=args.include_draft,
            )
        except LLMError as exc:
            print(f"The embedding model is not available: {type(exc).__name__}", file=sys.stderr)
            return 3
        except EmptyKeepListError:
            print("Refusing to retire the whole knowledge base.", file=sys.stderr)
            return 2
    finally:
        container.close()
    write_artifacts(
        report,
        args.processed,
        args.manifest,
        embedding_model=ollama.embedding_model,
        dimensions=ollama.embedding_dimensions,
        chunk_chars=kb.chunk_chars,
        chunk_overlap=kb.chunk_overlap,
    )
    if not report.notes:
        print("No approved notes: nothing was indexed and nothing was retired (an empty keep list is refused).")
    if args.include_draft:
        print("NOTE: --include-draft was given; drafts were indexed.")
    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
