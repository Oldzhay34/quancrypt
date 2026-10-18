"""UC1, UC2 and UC5 against the running stack and QBank (`make integration`, P4.6 acceptance).

Needs `make up PROFILES="app demo"` (or the equivalent compose project) with `PROJECT_ROOT=reference-system`, the host
Ollama (D-51) and the environment: `AGENT_SERVICE_URL` (default http://127.0.0.1:8083), `CORE_SERVICE_URL` (default
http://127.0.0.1:8081) and `QUANCRYPT_SESSION_TOKEN`. The analysis root is one QBank service (D-203). Without the stack
the tests fail; they never skip.

- UC1: the initial scan creates findings and a topology in core-service.
- UC2: "Servisler arasında RSA nerede?" answers with QBank file:line evidence.
- UC5: "Bana hava durumunu söyle" gets the fixed refusal.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from src.prompts.system_prompts import REFUSAL_TR

pytestmark = pytest.mark.integration

AGENT = os.environ.get("AGENT_SERVICE_URL", "http://127.0.0.1:8083")
CORE = os.environ.get("CORE_SERVICE_URL", "http://127.0.0.1:8081")
ROOT = os.environ.get("QUANCRYPT_ANALYSIS_ROOT", "/workspace/qbank-payment-service")
LOCATION = re.compile(r"^[^:\s]+:\d+$")


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['QUANCRYPT_SESSION_TOKEN']}", "X-Trace-Id": uuid.uuid4().hex}


def _sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    frames = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        frames.append((lines["event"], json.loads(lines["data"])))
    return frames


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=600, trust_env=False) as http:
        yield http


@pytest.fixture(scope="module")
def scanned(client: httpx.Client) -> dict[str, str]:
    """A fresh project, a Turkish session and a finished initial scan (UC1's work, asserted below)."""
    project = client.post(
        f"{CORE}/api/v1/projects",
        json={"identity": f"qbank-p46-{uuid.uuid4()}", "displayName": "QBank P4.6"},
        headers=_headers(),
    )
    assert project.status_code in (200, 201), project.text
    project_id = project.json()["id"]
    session = client.post(
        f"{AGENT}/api/v1/sessions", json={"project_id": project_id, "language": "tr"}, headers=_headers()
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]
    scan = client.post(f"{AGENT}/api/v1/sessions/{session_id}/initial-scan", json={"root": ROOT}, headers=_headers())
    assert scan.status_code == 200, scan.text
    frames = _sse(scan)
    assert frames[-1][0] == "done", frames[-3:]
    return {"project": project_id, "session": session_id}


def test_uc1_the_initial_scan_creates_findings_and_a_topology_in_core(
    client: httpx.Client, scanned: dict[str, str]
) -> None:
    scans = client.get(f"{CORE}/api/v1/projects/{scanned['project']}/scans", headers=_headers()).json()["items"]
    completed = [scan for scan in scans if scan["status"] == "COMPLETED"]
    assert completed, scans
    scan_id = completed[0]["id"]
    findings = client.get(f"{CORE}/api/v1/scans/{scan_id}/findings", params={"size": 200}, headers=_headers()).json()
    topology = client.get(f"{CORE}/api/v1/scans/{scan_id}/topology", headers=_headers())
    assert findings["totalElements"] > 0
    assert topology.status_code == 200 and topology.json()["nodes"]


def test_uc2_rsa_between_services_answers_with_qbank_file_line_evidence(
    client: httpx.Client, scanned: dict[str, str]
) -> None:
    response = client.post(
        f"{AGENT}/api/v1/sessions/{scanned['session']}/messages",
        json={"content": "Servisler arasında RSA nerede?"},
        headers=_headers(),
    )

    assert response.status_code == 200
    frames = _sse(response)
    assert frames[-1][0] == "done", frames[-3:]
    locations = [
        data["evidence"]["reference"]
        for event, data in frames
        if event == "evidence" and data["evidence"]["kind"] == "code_location"
    ]
    assert any(LOCATION.match(reference) for reference in locations), locations


def test_uc5_weather_gets_the_fixed_refusal(client: httpx.Client, scanned: dict[str, str]) -> None:
    response = client.post(
        f"{AGENT}/api/v1/sessions/{scanned['session']}/messages",
        json={"content": "Bana hava durumunu söyle"},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert _sse(response) == [("refusal", {"message": REFUSAL_TR, "language": "tr"})]
