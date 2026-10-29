"""The corpus: which projects are studied, how they are chosen and what becomes of each (P6.2, D-25, D-298).

Pure rules, no I/O. Selection is two-staged on purpose: the dataset says what it says (`SelectionPolicy` keeps what it
does not rule out), and the project itself is checked after cloning (license text, Spring Boot, at least three
services; `CloneCorpusService`), so a missing or wrong column of the dataset can never let an unfit project in."""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

# D-25: the prototype corpus targets 100 projects and must reach at least 50.
CORPUS_TARGET = 100
CORPUS_MINIMUM = 50
# A fixed seed: the same dataset always gives the same list, and a longer list starts with the shorter one.
SELECTION_SEED = 42
# MSR criterion (the dataset keeps projects with at least three microservices) and the license allow-list of the task.
MIN_SERVICES = 3
ALLOWED_LICENSES = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"})
# When the repository root cannot be analysed as one project, its sub-directories with a build file are (D-298b).
MAX_UNIT_DIRECTORIES = 20
MAX_UNIT_DEPTH = 2

_GITHUB_URL = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]{0,99})$"
)


_BENCHMARK_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def is_valid_benchmark_name(name: str) -> bool:
    """A benchmark code as the event schema and the corpus directory accept it (lower case, digits, hyphens)."""
    return _BENCHMARK_NAME.fullmatch(name) is not None


class InvalidRepoUrlError(ValueError):
    """The text is not an acceptable repository address. The message never repeats the text."""


@dataclass(frozen=True)
class RepoRef:
    """A GitHub repository. Only `https://github.com/<owner>/<name>` is accepted: no other host, scheme, user info,
    query, port or path, so the address cannot select another git transport or reach another machine."""

    owner: str
    name: str

    @classmethod
    def parse(cls, text: str) -> RepoRef:
        cleaned = text.strip().rstrip("/")
        cleaned = cleaned.removesuffix(".git")
        match = _GITHUB_URL.fullmatch(cleaned)
        if match is None or match["name"].endswith("."):
            raise InvalidRepoUrlError("not a https://github.com/<owner>/<name> address")
        return cls(match["owner"], match["name"])

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"

    @property
    def canonical(self) -> str:
        """The identity of the repository (GitHub ignores case): what the project key is derived from."""
        return self.url.lower()

    @property
    def dir_name(self) -> str:
        """The directory of the clone below the corpus root, and of the analyzer's `/corpus/<dir_name>`."""
        return f"{self.owner}__{self.name}".lower()


@dataclass(frozen=True)
class Candidate:
    """A project of the dataset. None means the dataset does not say."""

    repo: RepoRef
    default_branch: str | None
    license_spdx: str | None
    language: str | None
    service_count: int | None


@dataclass(frozen=True)
class SelectedProject:
    candidate: Candidate
    reason: str


class Rejection(StrEnum):
    """Why the dataset rules out a candidate (counted in the report of the list)."""

    NOT_JAVA = "not-java"
    TOO_FEW_SERVICES = "fewer-than-3-services"
    LICENSE_NOT_ALLOWED = "license-not-allowed"
    DUPLICATE = "duplicate"


class SelectionPolicy:
    """Keeps a candidate unless the dataset itself rules it out; what the dataset does not say is checked after
    cloning."""

    def __init__(self, seed: int = SELECTION_SEED) -> None:
        self._seed = seed

    def rejection(self, candidate: Candidate) -> Rejection | None:
        if candidate.language is not None and candidate.language.strip().casefold() != "java":
            return Rejection.NOT_JAVA
        if candidate.service_count is not None and candidate.service_count < MIN_SERVICES:
            return Rejection.TOO_FEW_SERVICES
        if candidate.license_spdx is not None and candidate.license_spdx not in ALLOWED_LICENSES:
            return Rejection.LICENSE_NOT_ALLOWED
        return None

    def select(self, candidates: Sequence[Candidate], size: int) -> tuple[list[SelectedProject], dict[Rejection, int]]:
        """The first `size` of a seeded shuffle of the candidates that pass, and how many each rule turned away."""
        turned_away: dict[Rejection, int] = {}
        seen: set[str] = set()
        kept: list[Candidate] = []
        for candidate in sorted(candidates, key=lambda c: c.repo.canonical):
            if candidate.repo.canonical in seen:
                turned_away[Rejection.DUPLICATE] = turned_away.get(Rejection.DUPLICATE, 0) + 1
                continue
            seen.add(candidate.repo.canonical)
            reason = self.rejection(candidate)
            if reason is not None:
                turned_away[reason] = turned_away.get(reason, 0) + 1
                continue
            kept.append(candidate)
        random.Random(self._seed).shuffle(kept)  # noqa: S311 (a reproducible sample, not a secret)
        return [SelectedProject(c, _reason(c)) for c in kept[:size]], turned_away


def _reason(candidate: Candidate) -> str:
    language = "java" if candidate.language else "language: to verify"
    services = f"services>={MIN_SERVICES}" if candidate.service_count is not None else "services: to verify"
    license_text = f"license {candidate.license_spdx}" if candidate.license_spdx else "license: to verify"
    return f"{language}; {services}; {license_text}"


class CloneStatus(StrEnum):
    SELECTED = "selected"
    CLONED = "cloned"
    EXCLUDED = "excluded"
    FAILED = "failed"


class ExclusionReason(StrEnum):
    LICENSE_UNVERIFIED = "license-unverified"
    NO_SPRING_BOOT = "no-spring-boot"
    TOO_FEW_SERVICES = "fewer-than-3-services"
    CLONE_FAILED = "clone-failed"


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    ANALYZED = "analyzed"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class ManifestEntry:
    """What has become of a project: one row of `reports/corpus_manifest.csv`. The commit id stays here and never goes
    into an event: it identifies the repository."""

    repo_url: str
    status: CloneStatus = CloneStatus.SELECTED
    exclusion_reason: ExclusionReason | None = None
    commit_sha: str | None = None
    license_verified: str | None = None
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    findings_total: int = 0
    units: int = 0
    analyzed_at: str | None = None


@dataclass(frozen=True)
class Eligibility:
    """The checks made on a clone: the first failing one is the reason it is left out."""

    license_spdx: str | None
    has_spring_boot: bool
    service_directories: int

    def exclusion(self) -> ExclusionReason | None:
        if self.license_spdx is None or self.license_spdx not in ALLOWED_LICENSES:
            return ExclusionReason.LICENSE_UNVERIFIED
        if not self.has_spring_boot:
            return ExclusionReason.NO_SPRING_BOOT
        if self.service_directories < MIN_SERVICES:
            return ExclusionReason.TOO_FEW_SERVICES
        return None
