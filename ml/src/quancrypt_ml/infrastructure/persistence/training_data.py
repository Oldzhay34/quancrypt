"""TrainingDataSource over marts.mart_risk_features (P7.2): the features, the gold label (labels schema, D-324d) and the
silver label (the rule table), corpus and benchmark rows only (D-317h). The application role reads marts."""

from __future__ import annotations

from sqlalchemy import Engine, text

from quancrypt_ml.domain.risk_features import RiskRow

QUERY = (
    "SELECT finding_id::text, project_key, algorithm_family, quantum_status, usage_context, location_kind, priority, "
    "key_size_bits, mode, padding, hash, library, confidence::float8, in_test_code, hndl_exposure, is_outlier_project, "
    "java_major, spring_boot_version, project_finding_count, gold_label, silver_label "
    "FROM marts.mart_risk_features ORDER BY finding_id"
)


class PostgresTrainingData:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def rows(self) -> list[RiskRow]:
        with self._engine.begin() as connection:
            result = connection.execute(text(QUERY)).all()
        return [
            RiskRow(
                finding_id=r[0],
                project_key=r[1],
                algorithm_family=r[2],
                quantum_status=r[3],
                usage_context=r[4],
                location_kind=r[5],
                priority=r[6],
                key_size_bits=r[7],
                mode=r[8],
                padding=r[9],
                hash=r[10],
                library=r[11],
                confidence=r[12],
                in_test_code=bool(r[13]),
                hndl_exposure=bool(r[14]),
                is_outlier_project=bool(r[15]),
                java_major=r[16],
                spring_boot_version=r[17],
                project_finding_count=int(r[18]),
                gold_label=r[19],
                silver_label=r[20],
            )  # fmt: skip
            for r in result
        ]
