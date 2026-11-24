"""The entry point of `quancrypt-data warehouse build` (P6.6)."""

from __future__ import annotations

from quancrypt_data.facade.corpus_facade import StepView
from quancrypt_data.port.inbound.build_warehouse import BuildWarehouseUseCase


class WarehouseBuildError(Exception):
    """dbt did not build the warehouse cleanly: a node or a test failed (the nodes are named)."""


class WarehouseFacade:
    def __init__(self, build: BuildWarehouseUseCase) -> None:
        self._build = build

    def build(self) -> StepView:
        result = self._build.execute()
        counts: dict[str, int] = {f"built_{kind}": count for kind, count in sorted(result.built.items())}
        counts.update(
            tests_passed=result.tests_passed,
            tests_failed=result.tests_failed,
            tests_warned=result.tests_warned,
            skipped=result.skipped,
            duration_s=round(result.duration_s),
        )
        view = StepView(counts, ())
        if not result.ok:
            raise WarehouseBuildError("dbt build failed: " + (", ".join(result.failed) or "no node was named"))
        return view
