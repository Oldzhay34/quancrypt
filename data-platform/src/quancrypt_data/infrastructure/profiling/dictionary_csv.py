"""`CanonicalDictionary` over contracts/canonical_dictionary.csv, the one dictionary analyzer-service also reads
(`kind,raw,algorithm_family,mode,padding,hash,usage_context,key_size_bits`)."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

VALUE_COLUMNS = ("mode", "padding", "hash")


class DictionaryError(Exception):
    """The canonical dictionary cannot be read. The message names the file, never its rows."""


class CsvCanonicalDictionary:
    def __init__(self, path: Path) -> None:
        try:
            with path.open(encoding="utf-8", newline="") as stream:
                self._rows = [row for row in csv.DictReader(stream) if row.get("raw")]
        except OSError:
            raise DictionaryError(f"cannot read the canonical dictionary {path.name}") from None
        if not self._rows or "kind" not in self._rows[0]:
            raise DictionaryError(f"the canonical dictionary {path.name} has no rows or no kind column")

    def raw_names(self) -> set[str]:
        return {row["raw"] for row in self._rows}

    def canonical_values(self) -> Mapping[str, set[str]]:
        values: dict[str, set[str]] = {column: set() for column in VALUE_COLUMNS}
        for row in self._rows:
            for column in VALUE_COLUMNS:
                if row.get(column):
                    values[column].add(row[column])
        return values
