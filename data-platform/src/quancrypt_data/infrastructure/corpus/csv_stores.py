"""The files the corpus tooling keeps: the corpus list (`reference/corpus_projects.csv`), the manifest of what became of
each project (`reports/corpus_manifest.csv`) and the report (`reports/corpus_run.md`). Plain CSV and text, written
atomically."""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from quancrypt_data.domain.corpus import (
    AnalysisStatus,
    CloneStatus,
    ExclusionReason,
    InvalidRepoUrlError,
    ManifestEntry,
    RepoRef,
    SelectedProject,
)

LIST_COLUMNS = ("repo_url", "default_branch", "license_spdx", "selection_reason")
MANIFEST_COLUMNS = (
    "repo_url",
    "status",
    "exclusion_reason",
    "commit_sha",
    "license_verified",
    "analysis_status",
    "findings_total",
    "units",
    "analyzed_at",
)


def _write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _csv_text(columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> str:
    lines: list[str] = []

    class _Lines:
        def write(self, text: str) -> int:
            lines.append(text)
            return len(text)

    writer = csv.DictWriter(_Lines(), fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return "".join(lines)


class CsvCorpusListStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write(self, projects: Sequence[SelectedProject]) -> None:
        rows = [
            {
                "repo_url": p.candidate.repo.url,
                "default_branch": p.candidate.default_branch or "",
                "license_spdx": p.candidate.license_spdx or "",
                "selection_reason": p.reason,
            }
            for p in projects
        ]
        _write_atomically(self._path, _csv_text(LIST_COLUMNS, rows))

    def read(self) -> Sequence[RepoRef]:
        if not self._path.exists():
            return []
        repos: list[RepoRef] = []
        with self._path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    repos.append(RepoRef.parse(row.get("repo_url", "")))
                except InvalidRepoUrlError:
                    continue
        return repos


class CsvManifestStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Mapping[str, ManifestEntry]:
        if not self._path.exists():
            return {}
        entries: dict[str, ManifestEntry] = {}
        with self._path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    repo = RepoRef.parse(row["repo_url"])
                    entries[repo.canonical] = ManifestEntry(
                        repo_url=repo.url,
                        status=CloneStatus(row["status"]),
                        exclusion_reason=ExclusionReason(row["exclusion_reason"]) if row["exclusion_reason"] else None,
                        commit_sha=row["commit_sha"] or None,
                        license_verified=row["license_verified"] or None,
                        analysis_status=AnalysisStatus(row["analysis_status"]),
                        findings_total=int(row["findings_total"]),
                        units=int(row["units"]),
                        analyzed_at=row["analyzed_at"] or None,
                    )
                except (KeyError, ValueError):
                    continue
        return entries

    def save(self, entries: Mapping[str, ManifestEntry]) -> None:
        rows = [
            {
                "repo_url": e.repo_url,
                "status": e.status.value,
                "exclusion_reason": e.exclusion_reason.value if e.exclusion_reason else "",
                "commit_sha": e.commit_sha or "",
                "license_verified": e.license_verified or "",
                "analysis_status": e.analysis_status.value,
                "findings_total": e.findings_total,
                "units": e.units,
                "analyzed_at": e.analyzed_at or "",
            }
            for _, e in sorted(entries.items())
        ]
        _write_atomically(self._path, _csv_text(MANIFEST_COLUMNS, rows))


class MarkdownReportWriter:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write(self, text: str) -> str:
        _write_atomically(self._path, text)
        return str(self._path)
