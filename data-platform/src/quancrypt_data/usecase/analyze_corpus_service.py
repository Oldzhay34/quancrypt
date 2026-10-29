from __future__ import annotations

import logging
from dataclasses import replace

from quancrypt_data.domain.corpus import AnalysisStatus, CloneStatus
from quancrypt_data.domain.corpus_events import CORPUS_ANALYSIS, build_events, repo_identifier
from quancrypt_data.port.inbound.corpus import AnalyzeCorpusCommand, AnalyzeCorpusResult, AnalyzeCorpusUseCase
from quancrypt_data.port.outbound.corpus import (
    CorpusListStore,
    EventDeliveryError,
    EventSink,
    ManifestStore,
    ProjectKeyHasher,
)
from quancrypt_data.port.outbound.system import Clock
from quancrypt_data.usecase.event_delivery import deliver
from quancrypt_data.usecase.project_analysis import ProjectAnalyzer

_LOG = logging.getLogger("quancrypt_data.usecase")


class AnalyzeCorpusService(AnalyzeCorpusUseCase):
    """Analyses the cloned projects of a window of the list and sends each result to ingest-api as `corpus_analysis`
    events.

    The project key is derived here, from the repository address, and only the key goes out (D-298a). A project whose
    delivery fails stays `failed` and is tried again next run; the event ids are derived, so a repeat is a duplicate."""

    def __init__(
        self,
        listing: CorpusListStore,
        manifest: ManifestStore,
        projects: ProjectAnalyzer,
        sink: EventSink,
        hasher: ProjectKeyHasher,
        clock: Clock,
    ) -> None:
        self._listing = listing
        self._manifest = manifest
        self._projects = projects
        self._sink = sink
        self._hasher = hasher
        self._clock = clock

    def execute(self, command: AnalyzeCorpusCommand) -> AnalyzeCorpusResult:
        window = self._listing.read()[command.offset : command.offset + command.limit]
        entries = dict(self._manifest.load())
        attempted = analyzed = unsupported = failed = findings = sent = accepted = duplicate = quarantined = 0
        for repo in window:
            entry = entries.get(repo.canonical)
            if entry is None or entry.status is not CloneStatus.CLONED:
                continue
            if entry.analysis_status in (AnalysisStatus.ANALYZED, AnalysisStatus.UNSUPPORTED):
                continue
            attempted += 1
            analysis = self._projects.analyze(repo.dir_name)
            if analysis.status is AnalysisStatus.ANALYZED:
                events = build_events(
                    CORPUS_ANALYSIS, self._hasher.key_for(repo_identifier(repo)), analysis.units, self._clock.now()
                )
                try:
                    delivery, requests = deliver(self._sink, events)
                except EventDeliveryError:
                    _LOG.warning("the events of a project could not be delivered")
                    failed += 1
                    entries[repo.canonical] = replace(entry, analysis_status=AnalysisStatus.FAILED)
                    self._manifest.save(entries)
                    continue
                total = sum(len(unit.findings) for unit in analysis.units)
                analyzed += 1
                findings += total
                sent += len(events)
                accepted += delivery.accepted
                duplicate += delivery.duplicate
                quarantined += delivery.quarantined
                _LOG.info(
                    "a project was analysed: %d units, %d findings, %d requests", len(analysis.units), total, requests
                )
                entries[repo.canonical] = replace(
                    entry,
                    analysis_status=AnalysisStatus.ANALYZED,
                    findings_total=total,
                    units=len(analysis.units),
                    analyzed_at=self._clock.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                )
            else:
                if analysis.status is AnalysisStatus.UNSUPPORTED:
                    unsupported += 1
                else:
                    failed += 1
                entries[repo.canonical] = replace(entry, analysis_status=analysis.status)
            self._manifest.save(entries)
        return AnalyzeCorpusResult(
            attempted=attempted,
            analyzed=analyzed,
            unsupported=unsupported,
            failed=failed,
            findings_total=findings,
            events_sent=sent,
            accepted=accepted,
            duplicate=duplicate,
            quarantined=quarantined,
        )
