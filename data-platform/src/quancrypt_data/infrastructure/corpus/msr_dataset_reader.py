"""Reads the MSR 2024 microservice dataset as a list of candidate projects (P6.2, D-304).

The file is the dataset's project list (`;`-separated, one row per repository, 49 columns). `ColumnMap` names the
columns this reader uses, as the real header spells them; a missing column is an error that lists the header it found,
so another file is never read by guesswork. The reader only turns cells into facts; which facts rule a project out is
the domain's `SelectionPolicy`."""

from __future__ import annotations

import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from quancrypt_data.domain.corpus import Candidate, InvalidRepoUrlError, RepoRef
from quancrypt_data.port.outbound.corpus import DatasetError

MAX_DATASET_BYTES = 200 * 1024 * 1024
# The longest cell of the dataset is about 290 KB (a JSON column); the csv module refuses more than 128 KiB by default.
MAX_FIELD_CHARS = 4 * 1024 * 1024
_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")


@dataclass(frozen=True)
class ColumnMap:
    """The dataset's column for each fact. Only `repo_url` is required; None means the file has no such column, and an
    empty cell means the dataset does not say (the project is then checked after cloning)."""

    repo_url: str = "URL"
    default_branch: str | None = None
    license_spdx: str | None = None
    languages: str | None = "languages"
    service_count: str | None = "n_microservices"
    archived: str | None = "Archived"
    work_in_progress: str | None = "WIP/Incomplete"
    application_type: str | None = "Application Type"


class CsvMsrDatasetReader:
    def __init__(self, columns: ColumnMap | None = None) -> None:
        self._columns = columns or ColumnMap()

    def read(self, path: Path) -> Sequence[Candidate]:
        try:
            if path.stat().st_size > MAX_DATASET_BYTES:
                raise DatasetError("the dataset file is larger than 200 MiB")
            stream = path.open(encoding="utf-8-sig", newline="")
        except OSError:
            raise DatasetError("the dataset file cannot be read") from None
        csv.field_size_limit(MAX_FIELD_CHARS)
        with stream:
            first = stream.readline()
            stream.seek(0)
            # The dataset is `;`-separated; a `,`-separated export of it is read the same way.
            delimiter = ";" if first.count(";") > first.count(",") else ","
            reader = csv.DictReader(stream, delimiter=delimiter)
            header = list(reader.fieldnames or [])
            wanted = [c for c in vars(self._columns).values() if c]
            missing = [c for c in wanted if c not in header]
            if missing:
                raise DatasetError(f"columns not found: {', '.join(missing)}; the file has: {', '.join(header)}")
            candidates: list[Candidate] = []
            try:
                for row in reader:
                    candidate = self._candidate(row)
                    if candidate is not None:
                        candidates.append(candidate)
            except csv.Error:
                raise DatasetError("the dataset file is not a readable CSV file") from None
        return candidates

    def _candidate(self, row: dict[str, str]) -> Candidate | None:
        columns = self._columns
        try:
            repo = RepoRef.parse(row.get(columns.repo_url) or "")
        except InvalidRepoUrlError:
            return None

        def text(column: str | None) -> str | None:
            value = (row.get(column) or "").strip() if column else ""
            return value or None

        services = text(columns.service_count)
        return Candidate(
            repo=repo,
            default_branch=text(columns.default_branch),
            license_spdx=text(columns.license_spdx),
            languages=_languages(text(columns.languages)),
            service_count=_count(services),
            archived=_yes_no(text(columns.archived)),
            work_in_progress=_yes_no(text(columns.work_in_progress)),
            application_type=text(columns.application_type),
        )


def _languages(value: str | None) -> frozenset[str] | None:
    """`['java', 'go']` (the dataset's spelling, read as plain text: nothing is evaluated) or a single name. An empty
    list says nothing."""
    if value is None:
        return None
    if value.startswith("[") and value.endswith("]"):
        names = [single or double for single, double in _QUOTED.findall(value[1:-1])]
    else:
        names = [value]
    found = frozenset(name.strip().casefold() for name in names if name.strip())
    return found or None


def _count(value: str | None) -> int | None:
    """An ASCII whole number of at most nine digits; anything else (a Unicode digit, a huge number) says nothing."""
    if value is None or not (value.isascii() and value.isdigit() and len(value) <= 9):
        return None
    return int(value)


def _yes_no(value: str | None) -> bool | None:
    if value is None:
        return None
    return {"yes": True, "no": False}.get(value.casefold())
