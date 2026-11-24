"""ReportWriter and ScopeDatasetFiles: plain text written atomically (a temporary file renamed over the target)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from quancrypt_ml.domain.scope import ScopeRecord
from quancrypt_ml.port.outbound.scope import ScopeDatasetError

_KEYS = ("id", "seed_id", "lang", "text", "label", "category", "source")
MAX_FILE_BYTES = 32 * 1024 * 1024


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


class FileReportWriter:
    def write(self, path: Path, text: str) -> None:
        _write(path, text)


class JsonlScopeDatasetFiles:
    def read(self, path: Path) -> list[ScopeRecord]:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ScopeDatasetError("the data set is larger than 32 MiB")
        records: list[ScopeRecord] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                raise ScopeDatasetError(f"line {number} is not JSON") from None
            if (
                not isinstance(item, dict)
                or set(item) != set(_KEYS)
                or not all(isinstance(item[k], str) for k in _KEYS)
            ):
                raise ScopeDatasetError(f"line {number}: the keys must be {', '.join(_KEYS)}, all strings")
            records.append(ScopeRecord(**{k: item[k] for k in _KEYS}))
        return records

    def write(self, path: Path, records: Sequence[ScopeRecord]) -> None:
        lines = (json.dumps(r.as_dict(), ensure_ascii=False, separators=(", ", ": ")) for r in records)
        _write(path, "".join(line + "\n" for line in lines))
