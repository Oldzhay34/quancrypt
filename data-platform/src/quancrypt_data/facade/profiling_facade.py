"""The entry point of `quancrypt-data profile` (P6.3)."""

from __future__ import annotations

from quancrypt_data.facade.corpus_facade import StepView
from quancrypt_data.port.inbound.profiling import ProfileRawDataUseCase


class RawDataChangedError(Exception):
    """The raw tables were not the same before and after profiling (another writer was running): the report says so."""


class ProfilingFacade:
    def __init__(self, profile: ProfileRawDataUseCase) -> None:
        self._profile = profile

    def profile(self) -> StepView:
        result = self._profile.execute()
        view = StepView(
            {
                "sources": result.sources,
                "findings": result.findings,
                "projects": result.projects,
                "unmapped_values": result.unmapped,
                "recommendations": result.recommendations,
            },
            tuple(f"written: {path}" for path in result.written),
        )
        if not result.unchanged:
            raise RawDataChangedError(
                "raw changed while it was being profiled (another writer ran); the report records both checksums"
            )
        return view
