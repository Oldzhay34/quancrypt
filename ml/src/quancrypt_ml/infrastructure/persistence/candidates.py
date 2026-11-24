"""LabelCandidateSource over marts.mart_risk_features (corpus and benchmark rows only, D-317h; the application role
reads it)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from quancrypt_ml.domain.labels import Candidate

_COLUMNS = (
    "finding_id::text, project_key, origin, algorithm_family, usage_context, location_kind, priority, in_test_code, "
    "key_size_bits, mode, padding, hash, library, confidence::float8, quantum_status, hndl_exposure"
)


class PostgresCandidateSource:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def candidates(self) -> list[Candidate]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text(f"SELECT {_COLUMNS} FROM marts.mart_risk_features ORDER BY finding_id")  # noqa: S608 (fixed text)
            ).all()
        return [Candidate(*row) for row in rows]

    def known(self, finding_ids: Sequence[str]) -> set[str]:
        if not finding_ids:
            return set()
        statement = text(
            "SELECT finding_id::text FROM marts.mart_risk_features WHERE finding_id = ANY(:ids)"
        ).bindparams(bindparam("ids", type_=ARRAY(UUID(as_uuid=False))))
        with self._engine.begin() as connection:
            return {row[0] for row in connection.execute(statement, {"ids": list(finding_ids)})}
