"""Example arguments and service replies for every HTTP tool (fabricated test data that fits the service contracts)."""

from __future__ import annotations

from typing import Any

PROJECT = "00000000-0000-0000-0000-00000000a001"
SCAN = "00000000-0000-0000-0000-00000000b001"
FINDING = "00000000-0000-0000-0000-00000000c001"
NOW = "2026-10-17T10:00:00Z"
KEY = "a" * 64

_PROJECT_BODY = {"id": PROJECT, "projectKey": KEY, "displayName": "QBank", "createdAt": NOW}
_SCAN_BODY = {
    "id": SCAN,
    "projectId": PROJECT,
    "status": "RUNNING",
    "startedAt": NOW,
    "completedAt": None,
    "runtimeProfileSequenceNo": None,
}
_TOPOLOGY_INPUT = {
    "nodes": [
        {"name": "qbank-gateway", "nodeKind": "GATEWAY"},
        {"name": "qbank-account-service", "nodeKind": "SERVICE"},
    ],
    "links": [
        {
            "source": "qbank-gateway",
            "target": "qbank-account-service",
            "protocol": "HTTP",
            "tls": True,
            "mtls": True,
            "callSites": [],
            "findingIds": [FINDING],
        }
    ],
}
_FINDING_BODY = {
    "id": FINDING,
    "scanId": SCAN,
    "path": "qbank-payment-service/src/main/java/Receipt.java",
    "symbol": "Receipt#sign",
    "algorithmFamily": "RSA",
    "usageContext": "SIGNATURE",
    "locationKind": "CODE",
    "priority": "P0",
    "keySizeBits": 1024,
    "lineStart": 12,
    "lineEnd": 14,
    "confidence": 0.9,
    "classifiedBy": "STATIC",
}
_PLAN_BODY = {"id": "00000000-0000-0000-0000-00000000d001", "scanId": SCAN, "createdAt": NOW, "itemCount": 1}
_CBOM = {"bomFormat": "CycloneDX", "specVersion": "1.6"}
_ANSWER = {"questionCode": "JDK_UPGRADE_POSSIBLE", "optionCode": "YES", "freeText": None}

# name -> (arguments, method, path, reply status, reply body (dict) or Markdown text, sends Idempotency-Key)
SAMPLES: dict[str, tuple[dict[str, Any], str, str, int, Any, bool]] = {
    "register_project": (
        {"body": {"identity": "/workspace/qbank", "displayName": "QBank"}},
        "POST",
        "/api/v1/projects",
        201,
        _PROJECT_BODY,
        True,
    ),
    "get_project": (
        {"projectId": PROJECT},
        "GET",
        f"/api/v1/projects/{PROJECT}",
        200,
        {"project": _PROJECT_BODY, "currentRuntimeProfile": None},
        False,
    ),
    "start_scan": ({"projectId": PROJECT}, "POST", f"/api/v1/projects/{PROJECT}/scans", 201, _SCAN_BODY, True),
    "record_findings": (
        {
            "scanId": SCAN,
            "body": {"findings": [{k: v for k, v in _FINDING_BODY.items() if k not in ("id", "scanId")}]},
        },
        "POST",
        f"/api/v1/scans/{SCAN}/findings",
        201,
        {"createdCount": 1, "existingCount": 0, "createdIds": [FINDING]},
        True,
    ),
    "record_scan_artifact": (
        {"scanId": SCAN, "body": _CBOM},
        "PUT",
        f"/api/v1/scans/{SCAN}/artifact",
        200,
        {"scanId": SCAN, "contentType": "application/vnd.cyclonedx+json", "sha256": "b" * 64, "createdAt": NOW},
        False,
    ),
    "record_topology": (
        {"scanId": SCAN, "body": _TOPOLOGY_INPUT},
        "PUT",
        f"/api/v1/scans/{SCAN}/topology",
        200,
        {"scanId": SCAN, "recordedAt": NOW} | _TOPOLOGY_INPUT,
        False,
    ),
    "complete_scan": (
        {"scanId": SCAN, "body": {"outcome": "COMPLETED"}},
        "POST",
        f"/api/v1/scans/{SCAN}/completion",
        200,
        _SCAN_BODY | {"status": "COMPLETED", "completedAt": NOW},
        True,
    ),
    "list_findings": (
        {"scanId": SCAN, "page": 0, "size": 50, "priority": "P0"},
        "GET",
        f"/api/v1/scans/{SCAN}/findings",
        200,
        {"items": [_FINDING_BODY], "page": 0, "size": 50, "totalElements": 1},
        False,
    ),
    "get_topology": (
        {"scanId": SCAN},
        "GET",
        f"/api/v1/scans/{SCAN}/topology",
        200,
        {"scanId": SCAN, "recordedAt": NOW} | _TOPOLOGY_INPUT,
        False,
    ),
    "get_project_profile": (
        {"projectId": PROJECT},
        "GET",
        f"/api/v1/projects/{PROJECT}/profile",
        200,
        {"runtimeProfile": None, "answers": []},
        False,
    ),
    "save_clarification_answers": (
        {"projectId": PROJECT, "body": {"answers": [_ANSWER]}},
        "PUT",
        f"/api/v1/projects/{PROJECT}/clarification-answers",
        200,
        {"answers": [_ANSWER]},
        False,
    ),
    "create_plan": (
        {"scanId": SCAN, "body": {"items": [{"findingId": FINDING, "riskScore": 0.9, "riskFactors": []}]}},
        "POST",
        f"/api/v1/scans/{SCAN}/plan",
        201,
        _PLAN_BODY,
        True,
    ),
    "get_plan": (
        {"scanId": SCAN, "page": 0, "size": 20},
        "GET",
        f"/api/v1/scans/{SCAN}/plan",
        200,
        {"plan": _PLAN_BODY, "items": [], "page": 0, "size": 20, "totalElements": 0},
        False,
    ),
    "get_plan_report": (
        {"scanId": SCAN, "language": "en"},
        "GET",
        f"/api/v1/scans/{SCAN}/plan/report",
        200,
        "# Migration plan\n\n1 item.\n",
        False,
    ),
    "get_consents": (
        {"projectId": PROJECT},
        "GET",
        f"/api/v1/projects/{PROJECT}/consents",
        200,
        {
            "items": [
                {
                    "consentType": "WAREHOUSE_ANALYTICS",
                    "privacyNoticeVersion": 1,
                    "grantedAt": NOW,
                    "revokedAt": None,
                    "version": 0,
                }
            ]
        },
        False,
    ),
    "analyze_crypto": (
        {"body": {"root": "/workspace/qbank-payment-service", "include_tests": True}},
        "POST",
        "/api/v1/analyses",
        200,
        {
            "analysis_id": "00000000-0000-0000-0000-00000000e001",
            "project_type": "GRADLE",
            "runtime": {"java_version": "25", "spring_boot_version": "4.1.1"},
            "findings": [],
            "cbom": _CBOM,
            "stats": {"files_scanned": 10, "findings_total": 0, "duration_ms": 120},
        },
        False,
    ),
    "build_topology": (
        {"body": {"root": "/workspace/qbank-payment-service"}},
        "POST",
        "/api/v1/topologies",
        200,
        {"nodes": [], "edges": []},
        False,
    ),
    "get_snippet": (
        {"root": "/workspace/qbank-payment-service", "path": "src/main/java/Receipt.java", "line": 12, "context": 1},
        "GET",
        "/api/v1/snippets",
        200,
        {
            "path": "src/main/java/Receipt.java",
            "lines": [
                {"number": 11, "text": "// sign the receipt"},
                {"number": 12, "text": 'Signature s = Signature.getInstance("SHA1withRSA");'},
                {"number": 13, "text": 'String password = "hunter2-secret";'},
            ],
        },
        False,
    ),
}
