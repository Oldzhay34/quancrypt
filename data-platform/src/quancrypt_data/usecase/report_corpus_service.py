from __future__ import annotations

from quancrypt_data.domain.corpus import AnalysisStatus
from quancrypt_data.domain.corpus_report import render_report
from quancrypt_data.port.inbound.corpus import ReportCorpusResult, ReportCorpusUseCase
from quancrypt_data.port.outbound.corpus import CorpusListStore, ManifestStore, ReportWriter
from quancrypt_data.port.outbound.system import Clock


class ReportCorpusService(ReportCorpusUseCase):
    """Writes `reports/corpus_run.md` from the manifest."""

    def __init__(self, listing: CorpusListStore, manifest: ManifestStore, writer: ReportWriter, clock: Clock) -> None:
        self._listing = listing
        self._manifest = manifest
        self._writer = writer
        self._clock = clock

    def execute(self) -> ReportCorpusResult:
        listed = len(self._listing.read())
        entries = list(self._manifest.load().values())
        path = self._writer.write(render_report(entries, listed, self._clock.now()))
        analyzed = sum(1 for e in entries if e.analysis_status is AnalysisStatus.ANALYZED)
        return ReportCorpusResult(path=path, listed=listed, analyzed=analyzed)
