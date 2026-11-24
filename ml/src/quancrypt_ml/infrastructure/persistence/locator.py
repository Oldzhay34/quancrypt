"""SourceLocator: the real file and line of a corpus finding (D-322b).

prep keeps an anonymised path (D-308b), so the location is read back from the raw event the finding came from: prep's
row id is uuid5 of (source event, "finding", ordinal) (data-platform `domain/prep.row_id`), the ordinal indexes the
event's `findings`, and the event's `analysis_unit` is the analysed unit below the clone. The clone directory comes from
the corpus manifest: the project key is HMAC-SHA256(QUANCRYPT_ANON_SALT, "corpus:" + canonical repository address)
(data-platform `domain/corpus_events`, D-301b), the directory `<owner>__<name>` in lower case. This is the one recorded
exception to "raw is not read" of ml-pipeline section 2, and only the export uses it; the location goes to the
git-ignored CSV only."""

from __future__ import annotations

import csv
import hashlib
import hmac
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy import Engine, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from quancrypt_ml.domain.labels import SourceLocation

# data-platform domain/prep.py (_ROW_NAMESPACE); a unit test pins a row id computed there.
ROW_NAMESPACE = uuid.UUID("6c1b9a3e-5f0d-4a59-9d8e-0b6f0e3c2a11")
ROOT_UNIT = "."
ANALYZER_CORPUS_ROOT = "/corpus"
_GITHUB = re.compile(r"https://github\.com/(?P<owner>[A-Za-z0-9-]{1,39})/(?P<name>[A-Za-z0-9._-]{1,100})")
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9._-]{1,255}")


def row_id(event_id: str, ordinal: int) -> str:
    return str(uuid.uuid5(ROW_NAMESPACE, f"{event_id}:finding:{ordinal}"))


def corpus_key(salt: str, owner: str, name: str) -> str:
    identifier = f"corpus:https://github.com/{owner}/{name}".lower()
    return hmac.new(salt.encode("utf-8"), identifier.encode("utf-8"), hashlib.sha256).hexdigest()


def clone_dirs(salt: str, manifest: Path) -> dict[str, str]:
    """project key -> clone directory, for every repository of the manifest (a missing manifest gives none)."""
    if not manifest.is_file():
        return {}
    result: dict[str, str] = {}
    with manifest.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            match = _GITHUB.fullmatch((row.get("repo_url") or "").strip().removesuffix(".git").rstrip("/"))
            if match is not None:
                owner, name = match["owner"], match["name"]
                result[corpus_key(salt, owner, name)] = f"{owner}__{name}".lower()
    return result


def _relative(path: object) -> str | None:
    """A path below the analysis root, or None (absolute, `..`, odd characters: the analyzer would refuse it anyway)."""
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        return None
    parts = path.split("/")
    if any(p in ("", ".", "..") or _SAFE_SEGMENT.fullmatch(p) is None for p in parts):
        return None
    return path


def location_in_event(
    finding_id: str, event_id: str, payload: Mapping[str, object], clone_dir: str
) -> SourceLocation | None:
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return None
    for ordinal, item in enumerate(findings):
        if row_id(event_id, ordinal) != finding_id:
            continue
        if not isinstance(item, Mapping):
            return None
        unit = payload.get("analysis_unit")
        unit = unit if isinstance(unit, str) else ROOT_UNIT
        file = _relative(item.get("file"))
        line = item.get("line_start")
        if file is None or (unit != ROOT_UNIT and _relative(unit) is None):
            return None
        root = f"{ANALYZER_CORPUS_ROOT}/{clone_dir}" + ("" if unit == ROOT_UNIT else f"/{unit}")
        return SourceLocation(root, file, line if isinstance(line, int) and not isinstance(line, bool) else None)
    return None


class PostgresSourceLocator:
    def __init__(self, engine: Engine, salt: str, manifest: Path) -> None:
        self._engine = engine
        self._salt = salt
        self._manifest = manifest

    def locate(self, finding_ids: Sequence[str]) -> dict[str, SourceLocation]:
        if not finding_ids:
            return {}
        dirs = clone_dirs(self._salt, self._manifest)
        statement = text(
            "SELECT f.id::text, f.source_event_id::text, f.project_key, e.payload "
            "FROM prep.finding f JOIN raw.event e ON e.event_id = f.source_event_id "
            "WHERE f.id = ANY(:ids) AND e.event_type = 'corpus_analysis'"
        ).bindparams(bindparam("ids", type_=ARRAY(UUID(as_uuid=False))))
        with self._engine.begin() as connection:
            rows = connection.execute(statement, {"ids": list(finding_ids)}).all()
        result: dict[str, SourceLocation] = {}
        for finding_id, event_id, project_key, payload in rows:
            clone = dirs.get(project_key)
            if clone is None or not isinstance(payload, Mapping):
                continue
            location = location_in_event(finding_id, event_id, payload, clone)
            if location is not None:
                result[finding_id] = location
        return result
