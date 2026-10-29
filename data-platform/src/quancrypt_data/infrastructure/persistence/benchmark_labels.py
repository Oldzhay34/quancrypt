"""PostgreSQL adapter of `BenchmarkLabelStore` (raw.benchmark_label): a benchmark is reloaded by deleting its rows and
writing the new ones in one transaction, so a failed load leaves the old labels."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from quancrypt_data.infrastructure.persistence.database import Database
from quancrypt_data.port.outbound.corpus import BenchmarkLabel
from quancrypt_data.port.outbound.system import Clock


class PostgresBenchmarkLabelStore:
    def __init__(self, database: Database, clock: Clock) -> None:
        self._database = database
        self._clock = clock

    def replace(self, benchmark: str, labels: Sequence[BenchmarkLabel]) -> int:
        def work() -> int:
            connection = self._database.connection()
            # Two loads of one benchmark at once would leave the union of both label sets (READ COMMITTED: the second
            # DELETE does not see the rows the first one is about to commit): one load at a time, per benchmark.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"),
                {"name": "quancrypt-benchmark:" + benchmark},
            )
            connection.execute(
                text("DELETE FROM raw.benchmark_label WHERE benchmark = :benchmark"), {"benchmark": benchmark}
            )
            connection.execute(
                text("DELETE FROM raw.benchmark_load WHERE benchmark = :benchmark"), {"benchmark": benchmark}
            )
            loaded_at = self._clock.now()
            if labels:
                connection.execute(
                    text(
                        "INSERT INTO raw.benchmark_label "
                        "(benchmark, case_id, file_path, category, cwe, expected_vulnerable) "
                        "VALUES (:benchmark, :case_id, :file_path, :category, :cwe, :expected_vulnerable)"
                    ),
                    [
                        {
                            "benchmark": benchmark,
                            "case_id": label.case_id,
                            "file_path": label.file_path,
                            "category": label.category,
                            "cwe": label.cwe,
                            "expected_vulnerable": label.expected_vulnerable,
                        }
                        for label in labels
                    ],
                )
            connection.execute(
                text(
                    "INSERT INTO raw.benchmark_load (benchmark, loaded_at, label_count) "
                    "VALUES (:benchmark, :loaded_at, :label_count)"
                ),
                {"benchmark": benchmark, "loaded_at": loaded_at, "label_count": len(labels)},
            )
            return len(labels)

        return self._database.run(work)
