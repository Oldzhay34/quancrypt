"""BatchFiles: the CSV of a label batch (git-ignored, D-322a).

Written as UTF-8 with a byte order mark so that a spreadsheet shows Turkish letters; read back with `,` or `;` (a
spreadsheet in a Turkish locale saves with semicolons), the separator taken from the header line. A cell that a
spreadsheet would run as a formula (starting with =, +, -, @, tab or carriage return; the context is code of other
people's repositories) gets a leading apostrophe (D-309b precedent)."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from pathlib import Path

from quancrypt_ml.domain.labels import BatchRow

COLUMNS = (
    "finding_id", "double_label", "origin", "algorithm_family", "usage_context", "location_kind", "priority",
    "in_test_code", "key_size_bits", "mode", "padding", "hash", "library", "confidence", "quantum_status",
    "hndl_exposure", "file", "line", "context_status", "context", "label", "labeler", "notes",
)  # fmt: skip
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
MAX_FILE_BYTES = 16 * 1024 * 1024


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def _row(row: BatchRow) -> dict[str, str]:
    c = row.sampled.candidate
    values: dict[str, object] = {
        "finding_id": c.finding_id, "double_label": row.sampled.double_label, "origin": c.origin,
        "algorithm_family": c.algorithm_family, "usage_context": c.usage_context, "location_kind": c.location_kind,
        "priority": c.priority, "in_test_code": c.in_test_code, "key_size_bits": c.key_size_bits, "mode": c.mode,
        "padding": c.padding, "hash": c.hash, "library": c.library,
        "confidence": None if c.confidence is None else f"{c.confidence:.3f}", "quantum_status": c.quantum_status,
        "hndl_exposure": c.hndl_exposure, "file": None if row.location is None else row.location.path,
        "line": None if row.location is None else row.location.line, "context_status": row.context_status,
        "context": "\n".join(f"{n}: {line}" for n, line in row.context), "label": "", "labeler": "", "notes": "",
    }  # fmt: skip
    return {key: _cell(value) for key, value in values.items()}


class CsvBatchFiles:
    def write_batch(self, path: Path, rows: Sequence[BatchRow]) -> None:
        self.write_rows(path, [_row(r) for r in rows], COLUMNS)

    def write_rows(self, path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str] | None = None) -> None:
        header = list(columns) if columns is not None else (list(rows[0]) if rows else [])
        path.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: _cell(v) for k, v in row.items()} for row in rows)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(buffer.getvalue(), encoding="utf-8-sig", newline="")
        temporary.replace(path)

    def read_rows(self, path: Path) -> list[dict[str, str]]:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("the file is larger than 16 MiB")
        content = path.read_text(encoding="utf-8-sig")
        first_line = content.split("\n", 1)[0]
        delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
        reader = csv.DictReader(io.StringIO(content, newline=""), delimiter=delimiter)
        return [{key: value or "" for key, value in row.items() if key is not None} for row in reader]
