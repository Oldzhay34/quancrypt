"""Anonymizer (P6.4, filter 6, D-308b): no project-internal name, raw identifier or secret reaches prep.

- A path keeps its well-known segments (source layout, build output, common build and configuration file names) and its
  file extension; every other segment, the file name's stem included, becomes the first twelve hex digits of
  HMAC-SHA256(salt, "path:" + segment). The same segment gets the same digest everywhere, so the rows of one file, one
  unit and a benchmark label with its findings stay together.
- A path that is no project-relative path (absolute, a drive, `..`, a scheme `://`, `@`, a backslash) is a raw
  identifier: its row is set aside (`identifier-leak`).
- The text columns that remain (mode, padding, hash, library, versions, label category) are scanned with the redaction
  rules of contracts/redaction-rules.yaml: a match sets the row aside (`secret-match`).
The salt is QUANCRYPT_ANON_SALT (the project keys are already its HMAC, computed before raw)."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Sequence
from dataclasses import replace

from quancrypt_data.domain.prep import (
    ROOT_UNIT,
    FilterResult,
    FindingRow,
    LabelRow,
    PrepBatch,
    Rejection,
    UnitRow,
    event_unit,
)
from quancrypt_data.port.outbound.profiling import SecretScanner

KEPT_SEGMENTS = frozenset({
    "src", "main", "test", "java", "kotlin", "resources", "webapp", "config", "META-INF", "WEB-INF", "target",
    "build", "out", "generated", "node_modules",
})  # fmt: skip
# Whole file names that name a kind of build or configuration file, not a project.
KEPT_NAMES = frozenset({
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "application.yml",
    "application.yaml", "application.properties", "bootstrap.yml", "bootstrap.yaml", "bootstrap.properties",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile", "mosquitto.conf",
})  # fmt: skip
# File extensions that name a kind of file; any other extension can carry a name (`Foo.customer`), so it is hashed.
KEPT_EXTENSIONS = frozenset({
    "java", "kt", "kts", "groovy", "gradle", "xml", "properties", "yml", "yaml", "json", "toml", "conf", "cfg", "ini",
    "pem", "crt", "cer", "key", "pub", "p12", "pfx", "jks", "keystore", "sql", "sh", "md", "txt", "csv", "py", "js",
    "ts",
})  # fmt: skip
_DIGITS = 12
_RAW_IDENTIFIER = re.compile(r"^(/|[A-Za-z]:)|://|@|\\")


class IdentifierLeak(ValueError):
    """A path that is not a project-relative path."""


class Anonymizer:
    code = "Anonymizer"

    def __init__(self, salt: str, scanner: SecretScanner) -> None:
        if len(salt) < 32 or "CHANGE_ME" in salt:
            raise ValueError("the anonymisation salt must be at least 32 characters and not the placeholder")
        self._key = salt.encode("utf-8")
        self._scanner = scanner

    def segment(self, segment: str) -> str:
        return hmac.new(self._key, f"path:{segment}".encode(), hashlib.sha256).hexdigest()[:_DIGITS]

    def path(self, path: str, directory: bool = False) -> str:
        """A file path (the last segment is a file name) or, with `directory`, an analysis unit (every segment is a
        directory: a dot in it is no extension, `acme-billing.gateway` must not stay)."""
        if _RAW_IDENTIFIER.search(path) or ".." in path.split("/"):
            raise IdentifierLeak("path")
        if path == ROOT_UNIT:
            return path
        parts = path.split("/")
        name = None if directory else parts.pop()
        hashed = [d if d in KEPT_SEGMENTS else self.segment(d) for d in parts]
        if name is not None:
            stem, dot, extension = name.rpartition(".") if "." in name[1:] else (name, "", "")
            if name in KEPT_NAMES:
                hashed.append(name)
            elif dot and extension in KEPT_EXTENSIONS:
                hashed.append(f"{self.segment(stem)}{dot}{extension}")
            else:
                hashed.append(self.segment(name))
        return "/".join(hashed)

    def _clean(self, texts: Sequence[object]) -> bool:
        return not self._scanner.scan([t for t in texts if isinstance(t, str)])

    def apply(self, batch: PrepBatch) -> FilterResult:
        rejected: list[Rejection] = []
        units: dict[tuple[str, str], str] = {}
        leaked_units: set[tuple[str, str]] = set()
        for unit in batch.units:
            try:
                units[(unit.project_key, unit.unit_path)] = self.path(unit.unit_path, directory=True)
            except IdentifierLeak:
                leaked_units.add((unit.project_key, unit.unit_path))
        # The rows of a unit whose name is a raw identifier go with it, one rejection per event.
        for event in batch.events:
            if (event.project_key, event_unit(event)) in leaked_units:
                rows = sum(
                    1
                    for rows_ in (batch.findings, batch.topologies, batch.links)
                    for r in rows_
                    if r.source_event_id == event.event_id
                )
                rejected.append(
                    Rejection(self.code, "identifier-leak", "unit_path", event.project_key, event.event_id, rows=rows)
                )
        if leaked_units:
            batch = batch.without_events(r.raw_event_id for r in rejected if r.raw_event_id)
            batch = replace(batch, units=tuple(u for u in batch.units if (u.project_key, u.unit_path) in units))

        findings: list[FindingRow] = []
        for f in batch.findings:
            try:
                file_path = self.path(f.file_path) if isinstance(f.file_path, str) else f.file_path
            except IdentifierLeak:
                rejected.append(
                    Rejection(self.code, "identifier-leak", "finding.file_path", f.project_key, f.source_event_id)
                )
                continue
            if not self._clean([f.mode, f.padding, f.hash, f.library]):
                rejected.append(Rejection(self.code, "secret-match", "finding", f.project_key, f.source_event_id))
                continue
            findings.append(replace(f, file_path=file_path, unit_path=units[(f.project_key, f.unit_path)]))

        unit_rows: list[UnitRow] = []
        for u in batch.units:
            versions = [u.java_version, u.spring_boot_version]
            # A version that matches a rule is dropped, not the unit: the unit holds the other rows.
            unit_rows.append(
                replace(u, unit_path=units[(u.project_key, u.unit_path)])
                if self._clean(versions)
                else UnitRow(u.project_key, units[(u.project_key, u.unit_path)])
            )

        labels: list[LabelRow] = []
        for label in batch.labels:
            try:
                file_path = self.path(label.file_path) if isinstance(label.file_path, str) else label.file_path
            except IdentifierLeak:
                rejected.append(
                    Rejection(
                        self.code,
                        "identifier-leak",
                        "benchmark_label.file_path",
                        label=(label.benchmark, label.case_id),
                    )
                )
                continue
            if not self._clean([label.category, label.case_id]):
                rejected.append(
                    Rejection(self.code, "secret-match", "benchmark_label", label=(label.benchmark, label.case_id))
                )
                continue
            labels.append(replace(label, file_path=file_path))

        return FilterResult(
            replace(
                batch,
                units=tuple(unit_rows),
                findings=tuple(findings),
                topologies=tuple(replace(t, unit_path=units[(t.project_key, t.unit_path)]) for t in batch.topologies),
                links=tuple(replace(link, unit_path=units[(link.project_key, link.unit_path)]) for link in batch.links),
                labels=tuple(labels),
            ),
            tuple(rejected),
            notes={"paths_anonymised": sum(1 for f in findings if isinstance(f.file_path, str))},
        )
