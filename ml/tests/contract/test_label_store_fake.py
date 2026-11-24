"""The fake LabelStore passes the same contract as the PostgreSQL adapter (tests/integration/test_labels_postgres.py)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from quancrypt_ml.port.outbound.labeling import LabelStore
from tests.support.fakes import FakeLabelStore
from tests.support.label_store_cases import CASES


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.__name__)
def test_the_fake_label_store_keeps_the_contract(case: Callable[[LabelStore], None]) -> None:
    case(FakeLabelStore())
