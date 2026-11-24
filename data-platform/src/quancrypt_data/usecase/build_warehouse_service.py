from __future__ import annotations

from quancrypt_data.port.inbound.build_warehouse import BuildWarehouseResult, BuildWarehouseUseCase
from quancrypt_data.port.outbound.warehouse import WarehouseBuilder, WarehouseBuildLock


class BuildWarehouseService(BuildWarehouseUseCase):
    """The lock is taken before dbt starts and released after it ends, whatever happens in between: a build never runs
    while an erasure of a project key is in flight (KVKK, D-318a, D-319d)."""

    def __init__(self, lock: WarehouseBuildLock, builder: WarehouseBuilder) -> None:
        self._lock = lock
        self._builder = builder

    def execute(self) -> BuildWarehouseResult:
        with self._lock.held():
            outcome = self._builder.build()
        return BuildWarehouseResult(
            ok=outcome.ok,
            built=dict(outcome.built),
            tests_passed=outcome.tests_passed,
            tests_failed=outcome.tests_failed,
            tests_warned=outcome.tests_warned,
            skipped=outcome.skipped,
            failed=tuple(outcome.failed),
            duration_s=outcome.duration_s,
        )
