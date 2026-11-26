"""MiningDataSource over the marts (P7.4, D-337): the profiles of marts.mart_archetypes and the non-test library usages
of marts.mart_risk_features, corpus rows only, read in one REPEATABLE READ transaction. The application role reads
marts.

dbt rebuilds a mart by renaming a new table over the old one, and rows committed after a read started are invisible to
it: such a mart would read as empty without an error. The read therefore locks both marts (ACCESS SHARE, the lock a
SELECT takes) before its first query, so a rebuild waits until the read has ended (D-341)."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import Connection, Engine, text

from quancrypt_ml.domain.mining import MiningSnapshot, ProjectLibraries, ProjectProfile

_LOCK_MARTS = "LOCK TABLE marts.mart_archetypes, marts.mart_risk_features IN ACCESS SHARE MODE"
_FAMILY, _CONTEXT = "share_alg_", "share_ctx_"
_PRIORITIES = ("p0", "p1", "p2", "p3")


def _shares(row: Mapping[str, object], prefix: str) -> dict[str, float]:
    return {
        name[len(prefix) :].upper(): float(str(value))
        for name, value in row.items()
        if name.startswith(prefix) and value is not None
    }


class PostgresMiningData:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def snapshot(self) -> MiningSnapshot:
        isolated = self._engine.connect().execution_options(isolation_level="REPEATABLE READ")
        with isolated as connection, connection.begin():
            connection.execute(text(_LOCK_MARTS))  # the first statement, before the snapshot is taken
            return MiningSnapshot(_profiles(connection), _libraries(connection), _with_findings(connection))


def _profiles(connection: Connection) -> list[ProjectProfile]:
    rows = connection.execute(
        text("SELECT * FROM marts.mart_archetypes WHERE origin = 'CORPUS' ORDER BY project_key")
    ).mappings()
    return [
        ProjectProfile(
            project_key=str(row["project_key"]),
            analysis_unit_count=int(row["analysis_unit_count"]),
            finding_count=int(row["finding_count"]),
            findings_per_unit=float(row["findings_per_unit"]),
            family_shares=_shares(dict(row), _FAMILY),
            context_shares=_shares(dict(row), _CONTEXT),
            priority_shares={p.upper(): float(row[f"share_{p}"] or 0.0) for p in _PRIORITIES},
        )
        for row in rows
    ]


def _libraries(connection: Connection) -> list[ProjectLibraries]:
    rows = connection.execute(
        text(
            "SELECT project_key, library, algorithm_family FROM marts.mart_risk_features "
            "WHERE origin = 'CORPUS' AND NOT in_test_code ORDER BY project_key, library, algorithm_family"
        )
    ).all()
    usages: dict[str, list[tuple[str | None, str]]] = {}
    for key, library, family in rows:
        known = None if library is None or str(library).startswith("~") else str(library)
        usages.setdefault(str(key), []).append((known, str(family)))
    return [ProjectLibraries(key, found) for key, found in usages.items()]


def _with_findings(connection: Connection) -> int:
    return int(
        connection.execute(
            text("SELECT count(DISTINCT project_key) FROM marts.mart_risk_features WHERE origin = 'CORPUS'")
        ).scalar_one()
    )
