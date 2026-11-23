from __future__ import annotations

from quancrypt_data.domain.profiling_report import build_report
from quancrypt_data.port.inbound.profiling import ProfileRawDataResult, ProfileRawDataUseCase
from quancrypt_data.port.outbound.profiling import (
    CanonicalDictionary,
    ProfileReportWriter,
    RawDataReader,
    SecretScanner,
)
from quancrypt_data.port.outbound.system import Clock


class ProfileRawDataService(ProfileRawDataUseCase):
    """Profiles raw (data-preprocessing section 2). Only reads: the row counts and digests of every raw table are taken
    before and after, and the report says whether they are equal (acceptance: no raw record changed)."""

    def __init__(
        self,
        reader: RawDataReader,
        dictionary: CanonicalDictionary,
        scanner: SecretScanner,
        writer: ProfileReportWriter,
        clock: Clock,
    ) -> None:
        self._reader = reader
        self._dictionary = dictionary
        self._scanner = scanner
        self._writer = writer
        self._clock = clock

    def execute(self) -> ProfileRawDataResult:
        before = self._reader.checksums()
        snapshot = self._reader.snapshot()
        hits = self._scanner.scan([sample.text for sample in snapshot.texts])
        after = self._reader.checksums()
        report = build_report(
            snapshot,
            known_raw_names=self._dictionary.raw_names(),
            known_values=self._dictionary.canonical_values(),
            secret_hits=hits,
            before=before,
            after=after,
            generated_at=self._clock.now(),
        )
        written = self._writer.write(report)
        return ProfileRawDataResult(
            written=tuple(written),
            sources=len(report.sources),
            findings=len(snapshot.findings),
            projects=len(report.per_project),
            unmapped=len(report.unmapped),
            recommendations=len(report.recommendations),
            unchanged=report.unchanged,
        )
