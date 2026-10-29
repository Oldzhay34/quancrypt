"""Reads the MSR 2024 microservice dataset as a list of candidate projects (P6.2).

TODO(P6.2-1): the dataset file has not been seen (figshare answered 403; D-298h). `ColumnMap` names the columns this
reader expects, with placeholder names; once the file is on disk its real header is compared with them and the mapping
is fixed. Until then the reader fails closed: a missing column is an error that lists the header it found, and nothing
is guessed."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from quancrypt_data.domain.corpus import Candidate, InvalidRepoUrlError, RepoRef
from quancrypt_data.port.outbound.corpus import DatasetError

MAX_DATASET_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class ColumnMap:
    """The dataset's column for each fact. Only `repo_url` is required; a column that is None or empty in the file means
    the dataset does not say (the project is then checked after cloning)."""

    repo_url: str = "repo_url"
    default_branch: str | None = None
    license_spdx: str | None = None
    language: str | None = None
    service_count: str | None = None


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
        with stream:
            reader = csv.DictReader(stream)
            header = list(reader.fieldnames or [])
            wanted = [c for c in vars(self._columns).values() if c]
            missing = [c for c in wanted if c not in header]
            if missing:
                raise DatasetError(f"columns not found: {', '.join(missing)}; the file has: {', '.join(header)}")
            candidates: list[Candidate] = []
            for row in reader:
                candidate = self._candidate(row)
                if candidate is not None:
                    candidates.append(candidate)
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
            language=text(columns.language),
            service_count=int(services) if services is not None and services.isdigit() else None,
        )
