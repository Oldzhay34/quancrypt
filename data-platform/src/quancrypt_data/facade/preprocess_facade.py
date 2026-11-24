"""The entry point of `quancrypt-data preprocess` (P6.4)."""

from __future__ import annotations

from quancrypt_data.facade.corpus_facade import StepView
from quancrypt_data.port.inbound.preprocess import PreprocessUseCase


class PrepLeakError(Exception):
    """The leak check found raw identifiers or secret patterns in prep (H6 must be zero): the report names the rules."""


class PreprocessFacade:
    def __init__(self, preprocess: PreprocessUseCase) -> None:
        self._preprocess = preprocess

    def preprocess(self) -> StepView:
        result = self._preprocess.execute()
        notes = [f"written: {path}" for path in result.written]
        if result.quarantine_warning:
            notes.append(f"warning: {result.quarantine_rate:.1%} of the rows were set aside (above 5%, D-310d)")
        if not result.projects_target_met:
            notes.append("target: fewer corpus projects than the minimum (D-306)")
        if not result.findings_target_met:
            notes.append("target: fewer findings than H5 asks (2000)")
        view = StepView(
            {
                "projects": result.projects,
                "findings": result.findings,
                "rows_in": result.rows_in,
                "rows_set_aside": result.rows_rejected,
                "leaks": sum(result.leaks.values()),
            },
            tuple(notes),
        )
        if any(result.leaks.values()):
            raise PrepLeakError(
                "the leak check found matches in prep: "
                + ", ".join(f"{k}={v}" for k, v in sorted(result.leaks.items()))
            )
        return view
