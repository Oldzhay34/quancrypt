"""`CoreConsentReader`, the warehouse consent gate (`ConsentReader`, D-21, D-228, D-232a): only a granted and not
revoked WAREHOUSE_ANALYTICS consent reads as true; every failure reads as false (fail-closed)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
import pytest
import respx

from src.memory.short_term import ConsentReader
from src.tools.core_tool import CoreConsentReader
from tests.support.tool_samples import NOW, PROJECT
from tests.support.tools import CORE_URL, TRACE, build_registry

URL = f"{CORE_URL}/api/v1/projects/{PROJECT}/consents"


def consent(kind: str, revoked_at: str | None) -> dict[str, Any]:
    return {"consentType": kind, "privacyNoticeVersion": 1, "grantedAt": NOW, "revokedAt": revoked_at, "version": 0}


@pytest.fixture
def reader() -> ConsentReader:
    return CoreConsentReader(build_registry().call)


def read(reader: ConsentReader, reply: httpx.Response | Exception) -> bool:
    with respx.mock() as mock:
        route = mock.get(URL)
        if isinstance(reply, Exception):
            route.mock(side_effect=reply)
        else:
            route.mock(return_value=reply)
        result = reader.warehouse_consent(uuid.UUID(PROJECT), TRACE)
    assert route.call_count >= 1
    return result


def test_a_granted_and_not_revoked_warehouse_consent_is_true(reader: ConsentReader) -> None:
    items = [consent("MODEL_TRAINING", NOW), consent("WAREHOUSE_ANALYTICS", None)]

    assert read(reader, httpx.Response(200, json={"items": items})) is True


@pytest.mark.parametrize(
    "items",
    [
        [consent("WAREHOUSE_ANALYTICS", NOW)],  # revoked
        [consent("MODEL_TRAINING", None)],  # only the other consent
        [],  # never granted
    ],
    ids=["revoked", "other-consent-only", "none"],
)
def test_a_revoked_or_missing_warehouse_consent_is_false(reader: ConsentReader, items: list[dict[str, Any]]) -> None:
    assert read(reader, httpx.Response(200, json={"items": items})) is False


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(404, json={"type": "https://quancrypt.local/problems/not-found"}),
        httpx.Response(401),
        httpx.Response(503),
        httpx.Response(200, json={"items": "not-a-list"}),
        httpx.Response(200, json={"items": [{"consentType": "WAREHOUSE_ANALYTICS"}]}),
        httpx.Response(200, text="not json"),
        httpx.ConnectError("down"),
        httpx.ReadTimeout("slow"),
    ],
    ids=[
        "not-found",
        "unauthorized",
        "unavailable",
        "items-not-a-list",
        "incomplete-item",
        "not-json",
        "down",
        "timeout",
    ],
)
def test_every_failure_reads_as_no_consent_and_is_logged_without_details(
    reader: ConsentReader, reply: httpx.Response | Exception, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="src.tools"):
        assert read(reader, reply) is False
    assert any("treated as not given" in message for message in caplog.messages)
    assert all(PROJECT not in message for message in caplog.messages)
