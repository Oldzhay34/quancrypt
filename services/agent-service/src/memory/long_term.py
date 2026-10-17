"""Long-term memory: the knowledge base (D-13, D-233d). Ports, values and the pure logic around them.

`KnowledgeBase` is what agents and tools see. `EmbeddingKnowledgeBase` implements it on top of an `EmbeddingProvider`
and a
`KnowledgeRepository`; the repository (pgvector and SQL) lives in `memory_store.py`. Every hit carries `title`,
`version_tag` and, when the note has one, `source_url` (guardrails-security section 4: no claim without a source).

The version filter (D-227): a note may declare the Java major version and the Spring Boot major.minor version range
it applies
to (both bounds inclusive). A note without a range for a component applies to every version of it; an unknown runtime
version
does not filter (D-150: unknown counts as satisfied).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from src.llm.provider import EmbeddingProvider, LLMError
from src.memory.short_term import SHA256_HEX, InvalidRecordError, Language

SourceType = Literal["STANDARD", "JEP", "VENDOR_DOC", "SPECIFICATION", "GOVERNMENT_GUIDANCE", "INTERNAL"]
Component = Literal["JAVA", "SPRING_BOOT"]

DOC_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
URL = re.compile(r"^https://[^\s\x00-\x1f\x7f]+$")

_JAVA_VERSION = re.compile(r"^(?:1\.)?(\d{1,3})(?:[._\-+].*)?$")
_MAJOR_MINOR = re.compile(r"^(\d{1,4})(?:\.(\d{1,4}))?(?:[.\-+].*)?$")


# ---- runtime versions ----


def parse_java_major(version: str | None) -> int | None:
    """ "17" -> 17, "21.0.2" -> 21, "24-ea" -> 24, "1.8.0_292" -> 8 (the legacy 1.x scheme); anything else -> None."""
    if version is None:
        return None
    match = _JAVA_VERSION.match(version.strip())
    if match is None:
        return None
    major = int(match.group(1))
    return major if major > 0 else None


def parse_major_minor(version: str | None) -> tuple[int, int] | None:
    """ "3.5.4" -> (3, 5), "3.5" -> (3, 5), "4" -> (4, 0); anything else -> None."""
    if version is None:
        return None
    match = _MAJOR_MINOR.match(version.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


@dataclass(frozen=True)
class RuntimeVersions:
    """The project's runtime as far as it is known (core-service `RuntimeProfile`); None = unknown."""

    java_major: int | None = None
    spring_boot: tuple[int, int] | None = None

    @classmethod
    def from_strings(cls, java_version: str | None, spring_boot_version: str | None) -> RuntimeVersions:
        return cls(java_major=parse_java_major(java_version), spring_boot=parse_major_minor(spring_boot_version))


# ---- values ----


@dataclass(frozen=True)
class Applicability:
    """The inclusive version range a note applies to for one component; at least one bound is set."""

    component: Component
    min_version: tuple[int, int] | None = None
    max_version: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if self.min_version is None and self.max_version is None:
            raise InvalidRecordError("an applicability range needs at least one bound")
        for bound in (self.min_version, self.max_version):
            if bound is not None and (bound[0] < 0 or bound[1] < 0):
                raise InvalidRecordError("version bounds must not be negative")
        if self.component == "JAVA" and any(b is not None and b[1] != 0 for b in (self.min_version, self.max_version)):
            raise InvalidRecordError("a Java bound has no minor part")
        if self.min_version is not None and self.max_version is not None and self.min_version > self.max_version:
            raise InvalidRecordError("the lower version bound exceeds the upper one")

    def admits(self, runtime: RuntimeVersions) -> bool:
        """Whether a runtime in this version range may see the note. Unknown runtime version: admitted (D-150)."""
        if self.component == "JAVA":
            version = (runtime.java_major, 0) if runtime.java_major is not None else None
        else:
            version = runtime.spring_boot
        if version is None:
            return True
        if self.min_version is not None and version < self.min_version:
            return False
        return not (self.max_version is not None and version > self.max_version)


@dataclass(frozen=True)
class KnowledgeChunk:
    ordinal: int
    text: str
    embedding: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.ordinal < 1 or not self.text or "\x00" in self.text or not self.embedding:
            raise InvalidRecordError("a chunk needs an ordinal from 1, text without NUL characters and an embedding")


@dataclass(frozen=True)
class KnowledgeDocument:
    """One note as it is indexed: metadata, applicability, the chunking and model it was built with, and its chunks."""

    doc_key: str
    title: str
    source_url: str | None
    source_type: SourceType
    version_tag: str
    language: Language
    applicability: tuple[Applicability, ...]
    content_sha256: str
    embedding_model: str
    chunk_chars: int
    chunk_overlap: int
    chunks: tuple[KnowledgeChunk, ...]

    def __post_init__(self) -> None:
        if not DOC_KEY.fullmatch(self.doc_key):
            raise InvalidRecordError("doc_key must be lowercase letters, digits, dot, underscore or hyphen (1 to 64)")
        if not self.title.strip() or len(self.title) > 300:
            raise InvalidRecordError("title must be 1 to 300 characters")
        if not self.version_tag.strip() or len(self.version_tag) > 64:
            raise InvalidRecordError("version_tag must be 1 to 64 characters")
        if self.source_url is None:
            if self.source_type != "INTERNAL":
                raise InvalidRecordError("only INTERNAL notes may omit the source URL")
        elif len(self.source_url) > 1024 or not URL.fullmatch(self.source_url):
            raise InvalidRecordError("source_url must be an https address of at most 1024 characters")
        if not SHA256_HEX.fullmatch(self.content_sha256):
            raise InvalidRecordError("content_sha256 must be 64 lowercase hexadecimal digits")
        if not self.embedding_model or not 0 <= self.chunk_overlap < self.chunk_chars:
            raise InvalidRecordError("a model name and a chunking with 0 <= overlap < size are required")
        if len({a.component for a in self.applicability}) != len(self.applicability):
            raise InvalidRecordError("a component can appear once in the applicability list")
        if [c.ordinal for c in self.chunks] != list(range(1, len(self.chunks) + 1)):
            raise InvalidRecordError("chunk ordinals must run 1..n without gaps")


@dataclass(frozen=True)
class Fingerprint:
    """What decides whether an indexed note is current: the file, the model and the chunking."""

    doc_key: str
    content_sha256: str
    embedding_model: str
    chunk_chars: int
    chunk_overlap: int


@dataclass(frozen=True)
class KbHit:
    doc_key: str
    title: str
    source_url: str | None
    version_tag: str
    source_type: SourceType
    language: Language
    ordinal: int
    text: str
    # Cosine distance (0 = same direction, 2 = opposite); lower is closer.
    distance: float


@dataclass(frozen=True)
class UpsertOutcome:
    action: Literal["created", "updated", "unchanged"]


class EmptyKeepListError(InvalidRecordError):
    """`retire_documents` refuses an empty keep list: it would delete the whole knowledge base."""


class KnowledgeUnavailableError(InvalidRecordError):
    """The query could not be embedded (LLM-less mode or Ollama down); search is not possible without it."""


# ---- ports ----


class KnowledgeRepository(Protocol):
    def search_chunks(
        self, embedding: Sequence[float], embedding_model: str, runtime: RuntimeVersions, k: int
    ) -> tuple[KbHit, ...]: ...

    def is_current(self, fingerprint: Fingerprint) -> bool: ...

    def upsert_document(self, document: KnowledgeDocument, *, force: bool = False) -> UpsertOutcome: ...

    def retire_documents(self, keep: Sequence[str]) -> int: ...


class KnowledgeBase(Protocol):
    """The read face: what a tool or an agent may use (it cannot change the index)."""

    def search(self, query: str, runtime: RuntimeVersions, k: int | None = None) -> tuple[KbHit, ...]:
        """The `k` chunks closest to the query among the notes that apply to the runtime, closest first.

        Raises `KnowledgeUnavailableError` when the query cannot be embedded.
        """
        ...


class KnowledgeIndex(Protocol):
    """The write face: only `scripts/build_index.py` uses it (interface segregation)."""

    def is_current(self, fingerprint: Fingerprint) -> bool: ...

    def upsert_document(self, document: KnowledgeDocument, *, force: bool = False) -> UpsertOutcome: ...

    def retire_documents(self, keep: Sequence[str]) -> int: ...


class EmbeddingKnowledgeBase:
    """`KnowledgeBase` and `KnowledgeIndex` over an embedding provider and a repository (no SQL here)."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        embeddings: EmbeddingProvider,
        embedding_model: str,
        dimensions: int,
        default_k: int,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._model = embedding_model
        self._dimensions = dimensions
        self._default_k = default_k

    def search(self, query: str, runtime: RuntimeVersions, k: int | None = None) -> tuple[KbHit, ...]:
        if not query.strip():
            raise InvalidRecordError("the search query must not be blank")
        size = self._default_k if k is None else k
        if not 1 <= size <= 50:
            raise InvalidRecordError("k must be between 1 and 50")
        try:
            result = self._embeddings.embed([query])
        except LLMError as exc:
            raise KnowledgeUnavailableError("the query could not be embedded") from exc
        if len(result.vectors) != 1 or len(result.vectors[0]) != self._dimensions:
            raise KnowledgeUnavailableError("the embedding has an unexpected size")
        return self._repository.search_chunks(result.vectors[0], self._model, runtime, size)

    def is_current(self, fingerprint: Fingerprint) -> bool:
        return self._repository.is_current(fingerprint)

    def upsert_document(self, document: KnowledgeDocument, *, force: bool = False) -> UpsertOutcome:
        return self._repository.upsert_document(document, force=force)

    def retire_documents(self, keep: Sequence[str]) -> int:
        if not keep:
            raise EmptyKeepListError("an empty keep list would delete the whole knowledge base")
        return self._repository.retire_documents(keep)


# ---- chunking ----

_SENTENCE_END = re.compile(r"[.!?…](?=\s)")


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    """Split text into chunks of at most `chunk_chars` characters that share about `overlap` characters with the
    previous one.

    Deterministic. A cut prefers a paragraph break, then a sentence end, then a line break, then a space, then (only
    for a word longer than a chunk) a hard cut; the overlap starts at a word boundary, or at a whole line after a line
    break. `text` is stripped; blank text gives no chunk.
    """
    if chunk_chars < 1 or not 0 <= overlap < chunk_chars:
        raise InvalidRecordError("chunking needs size >= 1 and 0 <= overlap < size")
    body = text.strip()
    chunks: list[str] = []
    start = 0
    while start < len(body):
        window_end = min(start + chunk_chars, len(body))
        end = window_end if window_end == len(body) else _cut(body, start, window_end)
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(body):
            break
        start = _next_start(body, start, end, overlap)
    return chunks


def _cut(body: str, start: int, window_end: int) -> int:
    floor = start + max(1, (window_end - start) // 2)
    paragraph = body.rfind("\n\n", floor, window_end)
    if paragraph != -1:
        return paragraph + 2
    sentence = None
    for match in _SENTENCE_END.finditer(body, floor, window_end):
        sentence = match.end()
    if sentence is not None:
        return sentence
    # A line break first (a table row or a list item is not split), then a space.
    line = body.rfind("\n", floor, window_end)
    if line != -1:
        return line + 1
    space = body.rfind(" ", floor, window_end)
    return space + 1 if space != -1 else window_end


def _next_start(body: str, start: int, end: int, overlap: int) -> int:
    if overlap == 0:
        return end
    candidate = max(start + 1, end - overlap)
    if body[end - 1] == "\n":
        # The cut was at a line break: overlap with whole lines only (a table row is never started in the middle).
        line = body.find("\n", candidate - 1, end - 1)
        return line + 1 if line != -1 else end
    # Begin at a word boundary: advance to the character after the next whitespace (but never past `end`).
    while candidate < end and not body[candidate - 1].isspace():
        candidate += 1
    return min(candidate, end) if candidate > start else end
