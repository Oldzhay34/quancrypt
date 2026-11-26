"""The fixed parity set ml writes beside an ONNX model (P7.5, D-344a, D-346c): its file name and which rows it keeps.

agent-service checks its own ONNX runtime against these rows, so they must show every answer the model gives on the
parity rows: the rows are taken round-robin over the answers (risk classes for Model A, three-way decisions for
Model B) in their original order, up to a limit, instead of the first N rows."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def parity_path(model: Path) -> Path:
    return model.with_name(model.name.removesuffix(".onnx") + ".parity.json")


def balanced_rows(answers: Sequence[str], limit: int) -> list[int]:
    """Indices of at most `limit` rows, round-robin over the distinct answers (first-seen order), each answer's rows in
    their original order; the result is sorted. Every answer present is kept as long as `limit` allows."""
    if limit <= 0:
        return []
    groups: dict[str, list[int]] = {}
    for index, answer in enumerate(answers):
        groups.setdefault(answer, []).append(index)
    chosen: list[int] = []
    depth = 0
    while len(chosen) < limit and any(depth < len(rows) for rows in groups.values()):
        for rows in groups.values():
            if depth < len(rows) and len(chosen) < limit:
                chosen.append(rows[depth])
        depth += 1
    return sorted(chosen)
