"""Analysing one project directory of the corpus root: the repository root first, its service directories when the root
cannot be analysed as one project (D-298b)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from quancrypt_data.domain.corpus import MAX_UNIT_DEPTH, MAX_UNIT_DIRECTORIES, AnalysisStatus
from quancrypt_data.domain.corpus_events import ROOT_UNIT, UnitAnalysis, is_valid_unit
from quancrypt_data.port.outbound.corpus import (
    AnalysisFailedError,
    AnalysisUnsupportedError,
    CodeAnalyzer,
    CorpusFiles,
)

_LOG = logging.getLogger("quancrypt_data.usecase")


@dataclass(frozen=True)
class ProjectAnalysis:
    units: tuple[UnitAnalysis, ...]
    status: AnalysisStatus


class ProjectAnalyzer:
    """`mount` is where the analyzer sees the corpus root (`/corpus`, the read-only bind of docker-compose)."""

    def __init__(self, analyzer: CodeAnalyzer, files: CorpusFiles, mount: str) -> None:
        self._analyzer = analyzer
        self._files = files
        self._mount = mount.rstrip("/")

    def analyze(self, dir_name: str) -> ProjectAnalysis:
        root = f"{self._mount}/{dir_name}"
        try:
            unit = self._analyzer.analyze(root)
        except AnalysisUnsupportedError:
            return self._service_directories(dir_name, root)
        except AnalysisFailedError:
            return ProjectAnalysis((), AnalysisStatus.FAILED)
        try:
            topology = self._analyzer.topology(root)
        except AnalysisFailedError:
            topology = None
        return ProjectAnalysis((replace(unit, unit=ROOT_UNIT, topology=topology),), AnalysisStatus.ANALYZED)

    def _service_directories(self, dir_name: str, root: str) -> ProjectAnalysis:
        units: list[UnitAnalysis] = []
        failed = 0
        for directory in self._files.service_directories(dir_name, MAX_UNIT_DEPTH, MAX_UNIT_DIRECTORIES):
            if not is_valid_unit(directory):
                continue
            # A module inside a unit that was analysed is part of that unit already: its findings are not counted twice.
            if any(directory.startswith(done.unit + "/") for done in units):
                continue
            try:
                unit = self._analyzer.analyze(f"{root}/{directory}")
            except AnalysisUnsupportedError:
                continue
            except AnalysisFailedError:
                failed += 1
                continue
            units.append(replace(unit, unit=directory, topology=None))
        if failed:
            _LOG.warning("%d service directories of a project could not be analysed", failed)
        if units:
            return ProjectAnalysis(tuple(units), AnalysisStatus.ANALYZED)
        return ProjectAnalysis((), AnalysisStatus.FAILED if failed else AnalysisStatus.UNSUPPORTED)
